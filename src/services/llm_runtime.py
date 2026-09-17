"""Runtime state cho endpoint + model LLM (UI đổi được khi đang chạy).

Giống `src.guardrails.state`: .env là giá trị KHỞI TẠO, module này giữ giá trị
HIỆN HÀNH trong RAM. Ba loại endpoint:

- env:    Docker environment — LLM_BASE_URL / LLM_API_KEY / LLM_MODEL trong .env
- groq:   Groq API, model mặc định openai/gpt-oss-20b (không cần khai báo trong .env)
- custom: URL OpenAI-compatible bất kỳ, ví dụ Kaggle Ollama gateway qua ngrok

API key không bao giờ được trả ra ngoài; `public_view` chỉ báo có/không có key.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Any, Literal
from urllib.parse import urlparse

from src.config import get_settings
from src.services.model_catalog import DEFAULT_GROQ_MODEL, DEFAULT_OPENROUTER_MODEL

EndpointKind = Literal["env", "groq", "openrouter", "custom"]
ENDPOINT_KINDS: tuple[str, ...] = ("env", "groq", "openrouter", "custom")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class LLMEndpoint:
    kind: str
    base_url: str
    api_key: str
    model: str
    provider: str


_lock = threading.RLock()  # get_active -> _default -> preset cần re-entrant
_active: LLMEndpoint | None = None
# Kết nối custom đã lưu (base_url, api_key) — UI khai báo trước khi chọn model.
_custom: tuple[str, str] | None = None


def infer_provider(base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    if host.endswith("groq.com"):
        return "groq"
    if host.endswith("openrouter.ai"):
        return "openrouter"
    if urlparse(base_url).port == 11434 or "ollama" in host:
        return "ollama"
    return "openai-compatible"


def normalize_base_url(base_url: str) -> str:
    """Chuẩn hóa URL: bắt buộc http(s), bỏ '/' cuối, tự thêm /v1 nếu thiếu."""
    url = (base_url or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url phải là URL http(s) hợp lệ")
    if not parsed.path.rstrip("/").endswith("/v1"):
        url = f"{url}/v1"
    return url


def _provider_key(provider: str) -> str:
    """Key riêng của provider, fallback về LLM_API_KEY nếu .env đang trỏ đúng provider đó."""
    settings = get_settings()
    dedicated = {"groq": settings.GROQ_API_KEY, "openrouter": settings.OPENROUTER_API_KEY}.get(provider, "")
    if dedicated.strip():
        return dedicated.strip()
    if infer_provider(settings.LLM_BASE_URL) == provider:
        return settings.LLM_API_KEY.strip()
    return ""


def _custom_connection() -> tuple[str, str] | None:
    if _custom is not None:
        return _custom
    settings = get_settings()
    if settings.REMOTE_LLM_BASE_URL.strip():
        try:
            return normalize_base_url(settings.REMOTE_LLM_BASE_URL), settings.REMOTE_LLM_API_KEY.strip()
        except ValueError:
            return None
    return None


def preset(kind: str, model: str | None = None) -> LLMEndpoint:
    """Endpoint theo loại, chưa kích hoạt. Raises ValueError nếu chưa cấu hình."""
    settings = get_settings()
    if kind == "env":
        base_url = settings.LLM_BASE_URL.rstrip("/")
        provider = infer_provider(base_url)
        # Nếu LLM_API_KEY trống, dùng key riêng của provider (GROQ_API_KEY / OPENROUTER_API_KEY).
        api_key = settings.LLM_API_KEY.strip() or _provider_key(provider)
        # Ưu tiên provider suy từ base_url: nhãn LLM_PROVIDER trong .env hay bị bỏ quên khi đổi endpoint.
        label = settings.LLM_PROVIDER.strip()
        resolved = provider if provider != "openai-compatible" else (label or provider)
        return LLMEndpoint("env", base_url, api_key, model or settings.LLM_MODEL, resolved)
    if kind == "groq":
        return LLMEndpoint("groq", GROQ_BASE_URL, _provider_key("groq"), model or DEFAULT_GROQ_MODEL, "groq")
    if kind == "openrouter":
        return LLMEndpoint("openrouter", OPENROUTER_BASE_URL, _provider_key("openrouter"),
                           model or DEFAULT_OPENROUTER_MODEL, "openrouter")
    if kind == "custom":
        with _lock:
            connection = _custom_connection()
        if connection is None:
            raise ValueError("chưa khai báo endpoint custom (base_url)")
        base_url, api_key = connection
        return LLMEndpoint("custom", base_url, api_key, model or "", infer_provider(base_url))
    raise ValueError(f"unknown endpoint {kind!r}; expected one of: {', '.join(ENDPOINT_KINDS)}")


def _default() -> LLMEndpoint:
    kind = get_settings().LLM_ENDPOINT
    try:
        endpoint = preset(kind)
    except ValueError:
        endpoint = preset("env")
    return endpoint if endpoint.model else preset("env")


def get_active() -> LLMEndpoint:
    global _active
    with _lock:
        if _active is None:
            _active = _default()
        return _active


def set_custom_connection(base_url: str, api_key: str | None) -> tuple[str, str]:
    """Lưu URL/key custom. api_key=None giữ key cũ nếu cùng URL."""
    global _custom
    url = normalize_base_url(base_url)
    with _lock:
        previous = _custom_connection()
        if api_key is None:
            key = previous[1] if previous and previous[0] == url else ""
        else:
            key = api_key.strip()
        _custom = (url, key)
    return _custom


def set_active(endpoint: LLMEndpoint) -> tuple[LLMEndpoint, LLMEndpoint]:
    global _active
    if not endpoint.model:
        raise ValueError("model không được để trống")
    previous = get_active()
    with _lock:
        _active = endpoint
    return previous, endpoint


def with_model(endpoint: LLMEndpoint, model: str) -> LLMEndpoint:
    return replace(endpoint, model=model)


def reset_to_default() -> LLMEndpoint:
    global _active, _custom
    with _lock:
        _custom = None
        _active = None
    return get_active()


def public_view(endpoint: LLMEndpoint) -> dict[str, Any]:
    return {
        "kind": endpoint.kind,
        "base_url": endpoint.base_url,
        "model": endpoint.model,
        "provider": endpoint.provider,
        "has_api_key": bool(endpoint.api_key),
    }


def active_model() -> str:
    return get_active().model
