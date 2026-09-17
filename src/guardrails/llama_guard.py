"""Llama Guard — chốt kiểm duyệt nội dung bằng model phân loại chạy local.

Đây là một chốt RIÊNG, độc lập với profile none/basic/strict (các profile đó là
luật code). Llama Guard 3 phân loại hội thoại theo taxonomy MLCommons (S1–S14):
bạo lực, vũ khí, tự hại, nội dung tình dục... Nó KHÔNG phải bộ phát hiện prompt
injection (đó là Prompt Guard) — hai loại bổ sung cho nhau.

Chạy local mặc định bằng llama.cpp server (CPU) với GGUF Llama-Guard-3-1B Q4_K_M
(`make llama-guard-up`, cổng 8088). Server dùng chat template Llama Guard nhúng trong
GGUF (--jinja). Cũng chạy được với Ollama (`llama-guard3:1b`) hoặc Kaggle gateway —
chỉ cần endpoint OpenAI-compatible. Model trả về:

    safe
    unsafe\nS1,S10

Bật/tắt runtime qua POST /config/llama-guard (không restart). Khi guard lỗi:
fail_mode=closed chặn request, fail_mode=open cho qua và ghi action lỗi.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import OpenAI

from src.config import get_settings

LLAMA_GUARD_INPUT_REPLY = (
    "Yêu cầu này vi phạm chính sách an toàn nội dung nên không được xử lý. "
    "Tôi có thể tiếp tục hỗ trợ các câu hỏi chăm sóc khách hàng."
)
LLAMA_GUARD_OUTPUT_REPLY = (
    "Câu trả lời bị chặn vì vi phạm chính sách an toàn nội dung. "
    "Tôi có thể tiếp tục hỗ trợ các câu hỏi chăm sóc khách hàng."
)

LLAMA_GUARD_UNAVAILABLE_REPLY = (
    "Hệ thống kiểm duyệt nội dung tạm thời không khả dụng nên yêu cầu chưa được xử lý."
)

# Taxonomy Llama Guard 3 (MLCommons hazard categories).
CATEGORIES: dict[str, str] = {
    "S1": "Tội phạm bạo lực",
    "S2": "Tội phạm phi bạo lực",
    "S3": "Tội phạm liên quan tình dục",
    "S4": "Bóc lột tình dục trẻ em",
    "S5": "Phỉ báng",
    "S6": "Tư vấn chuyên môn nguy hiểm",
    "S7": "Xâm phạm quyền riêng tư",
    "S8": "Sở hữu trí tuệ",
    "S9": "Vũ khí gây thương vong hàng loạt",
    "S10": "Thù ghét",
    "S11": "Tự tử & tự hại",
    "S12": "Nội dung tình dục",
    "S13": "Bầu cử",
    "S14": "Lạm dụng code interpreter",
}

FailMode = Literal["closed", "open"]


@dataclass(frozen=True)
class GuardConfig:
    enabled: bool
    check_output: bool
    fail_mode: FailMode
    base_url: str
    model: str


@dataclass(frozen=True)
class GuardVerdict:
    stage: str  # input | output
    safe: bool | None  # None = lỗi, không phân loại được
    blocked: bool
    categories: tuple[str, ...] = ()
    raw: str = ""
    latency_s: float = 0.0
    error: str | None = None
    actions: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "safe": self.safe,
            "blocked": self.blocked,
            "categories": [{"code": c, "name": CATEGORIES.get(c, c)} for c in self.categories],
            "raw": self.raw,
            "latency_s": self.latency_s,
            "error": self.error,
            "actions": list(self.actions),
        }


_lock = threading.Lock()
_override: dict[str, Any] = {}
_clients: dict[tuple[str, str], OpenAI] = {}


def get_config() -> GuardConfig:
    settings = get_settings()
    with _lock:
        values = dict(_override)
    return GuardConfig(
        enabled=values.get("enabled", settings.LLAMA_GUARD_ENABLED),
        check_output=values.get("check_output", settings.LLAMA_GUARD_CHECK_OUTPUT),
        fail_mode=values.get("fail_mode", settings.LLAMA_GUARD_FAIL_MODE),
        base_url=settings.LLAMA_GUARD_BASE_URL.rstrip("/"),
        model=values.get("model", settings.LLAMA_GUARD_MODEL),
    )


def update_config(**changes: Any) -> tuple[GuardConfig, GuardConfig]:
    previous = get_config()
    allowed = {"enabled", "check_output", "fail_mode", "model"}
    with _lock:
        _override.update({k: v for k, v in changes.items() if k in allowed and v is not None})
    return previous, get_config()


def reset_to_default() -> GuardConfig:
    with _lock:
        _override.clear()
    return get_config()


def _client(base_url: str) -> OpenAI:
    settings = get_settings()
    key = (base_url, settings.LLAMA_GUARD_API_KEY or "ollama")
    with _lock:
        if key not in _clients:
            _clients[key] = OpenAI(
                base_url=base_url, api_key=key[1],
                timeout=settings.LLAMA_GUARD_TIMEOUT_SECONDS, max_retries=0,
                default_headers={"ngrok-skip-browser-warning": "true"},
            )
        return _clients[key]


def parse_output(text: str) -> tuple[bool | None, tuple[str, ...]]:
    """'safe' -> (True, ()); 'unsafe\\nS1,S10' -> (False, ('S1','S10')); khác -> (None, ())."""
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    if not lines:
        return None, ()
    head = lines[0].casefold()
    if head == "safe":
        return True, ()
    if head == "unsafe":
        codes = []
        for line in lines[1:]:
            codes.extend(code.strip().upper() for code in line.split(",") if code.strip())
        return False, tuple(dict.fromkeys(codes))
    return None, ()


def strip_assistant_prefill(raw: str, messages: list[dict[str, str]]) -> str:
    """llama.cpp coi tin nhắn assistant cuối là prefill và trả lại nó kèm kết quả.

    Ví dụ output stage: "<câu trả lời>unsafe\nS1" -> "unsafe\nS1". Ollama không echo.
    """
    if messages and messages[-1].get("role") == "assistant":
        prefix = (messages[-1].get("content") or "").strip()
        if prefix and raw.startswith(prefix):
            return raw[len(prefix):].strip()
    return raw


def classify(messages: list[dict[str, str]], stage: str, config: GuardConfig | None = None) -> GuardVerdict:
    """Phân loại hội thoại (kết thúc bằng user cho input, assistant cho output)."""
    config = config or get_config()
    started = time.monotonic()
    try:
        response = _client(config.base_url).chat.completions.create(
            model=config.model, messages=messages, temperature=0, max_tokens=20,
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = strip_assistant_prefill(raw, messages)
        safe, categories = parse_output(raw)
        error = None if safe is not None else "unexpected guard output"
    except Exception as exc:  # noqa: BLE001 — lỗi mạng/model được xử lý theo fail_mode
        raw, safe, categories, error = "", None, (), type(exc).__name__
    latency = round(time.monotonic() - started, 3)

    if safe is None:
        blocked = config.fail_mode == "closed"
        action = f"llama_guard_error:{stage}"
        return GuardVerdict(stage, None, blocked, (), raw[:200], latency, error, (action,))
    if safe:
        return GuardVerdict(stage, True, False, (), raw[:200], latency)
    actions = tuple(f"llama_guard_block:{stage}:{code}" for code in categories) or (
        f"llama_guard_block:{stage}",)
    return GuardVerdict(stage, False, True, categories, raw[:200], latency, None, actions)


def check_input(user_message: str, config: GuardConfig | None = None) -> GuardVerdict | None:
    config = config or get_config()
    if not config.enabled:
        return None
    return classify([{"role": "user", "content": user_message}], "input", config)


def check_output(user_message: str, reply: str, config: GuardConfig | None = None) -> GuardVerdict | None:
    config = config or get_config()
    if not (config.enabled and config.check_output):
        return None
    return classify(
        [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}],
        "output", config,
    )


def public_config(config: GuardConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    return {
        "enabled": config.enabled,
        "check_output": config.check_output,
        "fail_mode": config.fail_mode,
        "base_url": config.base_url,
        "model": config.model,
        "categories": [{"code": code, "name": name} for code, name in CATEGORIES.items()],
    }
