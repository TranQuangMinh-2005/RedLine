"""Prompt Guard 2 — chốt phát hiện prompt injection / jailbreak bằng model local.

Chốt RIÊNG, độc lập profile none/basic/strict và với Llama Guard:
- Llama Guard 3: nội dung độc hại (S1–S14), KHÔNG bắt trích xuất system prompt.
- Prompt Guard 2 86M: xác suất văn bản là tấn công injection/jailbreak (0..1).

Kiểm tra: các lượt user trong session (trước LLM) và, nếu bật check_rag, từng tài
liệu RAG trả về cho agent (indirect injection). Server: services/prompt_guard
(`make prompt-guard-up`, cổng 8089).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from src.config import get_settings

PROMPT_GUARD_REPLY = (
    "Yêu cầu có dấu hiệu tấn công prompt injection nên không được xử lý. "
    "Tôi có thể tiếp tục hỗ trợ các câu hỏi chăm sóc khách hàng."
)
PROMPT_GUARD_UNAVAILABLE_REPLY = (
    "Hệ thống phát hiện prompt injection tạm thời không khả dụng nên yêu cầu chưa được xử lý."
)
MAX_TURNS = 10

FailMode = Literal["closed", "open"]


@dataclass(frozen=True)
class PromptGuardConfig:
    enabled: bool
    threshold: float
    check_rag: bool
    fail_mode: FailMode
    url: str
    model: str


@dataclass(frozen=True)
class PromptGuardVerdict:
    scores: tuple[float, ...]
    threshold: float
    blocked: bool
    flagged_index: int | None = None
    latency_s: float = 0.0
    error: str | None = None
    actions: tuple[str, ...] = ()

    @property
    def max_score(self) -> float | None:
        return max(self.scores) if self.scores else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scores": list(self.scores),
            "max_score": self.max_score,
            "threshold": self.threshold,
            "blocked": self.blocked,
            "flagged_index": self.flagged_index,
            "latency_s": self.latency_s,
            "error": self.error,
            "actions": list(self.actions),
        }


_lock = threading.Lock()
_override: dict[str, Any] = {}


def get_config() -> PromptGuardConfig:
    settings = get_settings()
    with _lock:
        values = dict(_override)
    return PromptGuardConfig(
        enabled=values.get("enabled", settings.PROMPT_GUARD_ENABLED),
        threshold=values.get("threshold", settings.PROMPT_GUARD_THRESHOLD),
        check_rag=values.get("check_rag", settings.PROMPT_GUARD_CHECK_RAG),
        fail_mode=values.get("fail_mode", settings.PROMPT_GUARD_FAIL_MODE),
        url=settings.PROMPT_GUARD_URL.rstrip("/"),
        model=settings.PROMPT_GUARD_MODEL,
    )


def update_config(**changes: Any) -> tuple[PromptGuardConfig, PromptGuardConfig]:
    previous = get_config()
    allowed = {"enabled", "threshold", "check_rag", "fail_mode"}
    with _lock:
        _override.update({k: v for k, v in changes.items() if k in allowed and v is not None})
    return previous, get_config()


def reset_to_default() -> PromptGuardConfig:
    with _lock:
        _override.clear()
    return get_config()


def score_texts(texts: list[str], config: PromptGuardConfig | None = None) -> tuple[list[float], float]:
    """Gọi server Prompt Guard. Trả (scores, latency). Raises RuntimeError khi lỗi."""
    config = config or get_config()
    started = time.monotonic()
    try:
        response = httpx.post(f"{config.url}/classify", json={"texts": texts},
                              timeout=get_settings().PROMPT_GUARD_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise RuntimeError(type(exc).__name__) from exc
    if response.status_code != 200:
        detail = ""
        try:
            detail = str(response.json().get("detail") or "")
        except ValueError:
            pass
        raise RuntimeError(f"HTTP {response.status_code} {detail}".strip()[:200])
    results = response.json().get("results") or []
    if len(results) != len(texts):
        raise RuntimeError("unexpected prompt guard response")
    return [float(row["score"]) for row in results], round(time.monotonic() - started, 3)


def check_texts(texts: list[str], stage: str, config: PromptGuardConfig | None = None) -> PromptGuardVerdict:
    config = config or get_config()
    try:
        scores, latency = score_texts(texts, config)
    except RuntimeError as exc:
        return PromptGuardVerdict((), config.threshold, config.fail_mode == "closed",
                                  error=str(exc), actions=(f"prompt_guard_error:{stage}",))
    flagged = next((i for i, s in enumerate(scores) if s >= config.threshold), None)
    return PromptGuardVerdict(
        tuple(round(s, 4) for s in scores), config.threshold, flagged is not None, flagged, latency,
        actions=(f"prompt_guard_block:{stage}",) if flagged is not None else (),
    )


def check_messages(messages: list[dict[str, Any]], config: PromptGuardConfig | None = None) -> PromptGuardVerdict | None:
    """Kiểm tra tối đa MAX_TURNS lượt user gần nhất (injection có thể nằm ở lượt trước)."""
    config = config or get_config()
    if not config.enabled:
        return None
    texts = [str(m.get("content") or "") for m in messages if m.get("role") == "user"][-MAX_TURNS:]
    return check_texts(texts or [""], "input", config)


def filter_rag_result(result: dict[str, Any], config: PromptGuardConfig | None = None) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    """Loại tài liệu RAG có điểm injection >= threshold. Trả (result, actions, detail)."""
    config = config or get_config()
    rows = result.get("data")
    if not (config.enabled and config.check_rag) or not isinstance(rows, list) or not rows:
        return result, [], None
    texts = [str(row.get("text") or "") if isinstance(row, dict) else str(row) for row in rows]
    verdict = check_texts(texts, "rag", config)
    detail = {"scores": list(verdict.scores), "threshold": config.threshold, "error": verdict.error}
    if verdict.error:
        if config.fail_mode == "open":
            return result, list(verdict.actions), detail
        blocked = dict(result, ok=False, status="blocked", data=[],
                       error="retrieved content could not be screened for prompt injection")
        return blocked, list(verdict.actions), detail
    keep = [row for row, score in zip(rows, verdict.scores, strict=True) if score < config.threshold]
    if len(keep) == len(rows):
        return result, [], detail
    filtered = dict(result, data=keep, status="partial" if keep else "blocked")
    if not keep:
        filtered.update(ok=False, error="retrieved content failed the prompt injection screen")
    return filtered, ["prompt_guard_drop:rag"], detail


def public_config(config: PromptGuardConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    return {
        "enabled": config.enabled,
        "threshold": config.threshold,
        "check_rag": config.check_rag,
        "fail_mode": config.fail_mode,
        "url": config.url,
        "model": config.model,
    }
