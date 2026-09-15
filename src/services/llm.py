"""Wrapper gọi LLM (W1 task 1.3).

Dùng OpenAI-compatible SDK để gọi Groq (Imports: openai >= 1.0).
- Không hard-code key: đọc từ Settings (.env)
- Temperature 0.0 mặc định: tái lập được (tiêu chí 1.4)
- Trả về văn bản + metadata (model, tokens, latency) để W3 schema có dữ liệu
"""

from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from src.config import get_settings

# Singleton client — tránh tạo kết nối mới mỗi request
_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Lazy-init OpenAI client trỏ tới Groq hoặc Ollama."""
    global _client
    if _client is None:
        settings = get_settings()
        api_key = settings.LLM_API_KEY.strip() or "ollama"
        _client = OpenAI(
            api_key=api_key,
            base_url=settings.LLM_BASE_URL,
            timeout=120.0,
            max_retries=2,
        )
    return _client


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
        model=model or settings.LLM_MODEL,
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
