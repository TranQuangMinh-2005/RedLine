"""Wrapper gọi LLM (W1 task 1.3).

Dùng OpenAI-compatible SDK để gọi Groq (Imports: openai >= 1.0).
- Không hard-code key: đọc từ Settings (.env)
- Temperature 0.0 mặc định: tái lập được (tiêu chí 1.4)
- Trả về văn bản + metadata (model, tokens, latency) để W3 schema có dữ liệu
"""

from __future__ import annotations

import threading
import time
from typing import Any

from openai import OpenAI

from src.config import get_settings
from src.services import llm_runtime
from src.services.model_gateway import NGROK_HEADERS

# Cache client theo (base_url, api_key) — endpoint đổi runtime thì dùng client khác
_clients: dict[tuple[str, str], OpenAI] = {}
_clients_lock = threading.Lock()


def get_client() -> OpenAI:
    """OpenAI client trỏ tới endpoint đang hiệu lực (Groq, .env hoặc custom/Kaggle)."""
    endpoint = llm_runtime.get_active()
    api_key = endpoint.api_key or "ollama"
    cache_key = (endpoint.base_url, api_key)
    with _clients_lock:
        client = _clients.get(cache_key)
        if client is None:
            client = OpenAI(
                api_key=api_key,
                base_url=endpoint.base_url,
                timeout=get_settings().LLM_TIMEOUT_SECONDS,
                max_retries=2,
                default_headers=NGROK_HEADERS,
            )
            _clients[cache_key] = client
        return client


def chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = 1024,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
) -> dict[str, Any]:
    """Gửi hội thoại (multi-turn) tới LLM và trả về dict kết quả.

    Args:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: override model, mặc định dùng config
        temperature: override, mặc định 0.0
        max_tokens: giới hạn output

    Returns:
        {
            "text": str,
            "model": str,
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "latency_s": float,
            "finish_reason": str,
        }
    """
    settings = get_settings()
    client = get_client()

    t0 = time.time()
    request: dict[str, Any] = dict(
        model=model or llm_runtime.active_model(),
        messages=messages,
        temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
        max_tokens=max_tokens,
    )
    if tools:
        request["tools"] = tools
        request["tool_choice"] = tool_choice or "auto"
    resp = client.chat.completions.create(**request)
    latency = time.time() - t0

    choice = resp.choices[0]
    tool_calls = [
        {
            "id": call.id or f"call_{i}",
            "type": "function",
            "function": {"name": call.function.name, "arguments": call.function.arguments},
        }
        for i, call in enumerate(choice.message.tool_calls or [])
    ]
    return {
        "text": choice.message.content or "",
        "model": resp.model,
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
        "total_tokens": resp.usage.total_tokens if resp.usage else 0,
        "latency_s": round(latency, 3),
        "finish_reason": choice.finish_reason,
        "tool_calls": tool_calls,
    }


def summarize_error(exc: Exception) -> str:
    """Chuyển lỗi API thành chuỗi an toàn để log (không chứa key/secret)."""
    return type(exc).__name__
