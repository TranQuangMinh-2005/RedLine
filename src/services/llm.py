"""OpenAI-compatible LLM client with runtime model selection and provider routing."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from src.config import get_settings
from src.services import llm_runtime
from src.services.model_gateway import NGROK_HEADERS

_THINK_RE = re.compile(r"<think>(.*?)</think>\s*", re.DOTALL | re.IGNORECASE)


def split_reasoning(content: str, message: Any) -> tuple[str, str]:
    """Return user-visible text and provider reasoning as separate strings."""
    reasoning = ""
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(message, field, None)
        if isinstance(value, str) and value.strip():
            reasoning = value.strip()
            break
    embedded = _THINK_RE.findall(content or "")
    if embedded:
        embedded_reasoning = "\n".join(embedded).strip()
        reasoning = f"{reasoning}\n{embedded_reasoning}".strip() if reasoning else embedded_reasoning
        content = _THINK_RE.sub("", content or "").strip()
    return content or "", reasoning


@dataclass(frozen=True)
class ProviderSpec:
    slot: str
    name: str
    model: str
    api_key: str
    base_url: str


_clients: dict[tuple[str, str, str], OpenAI] = {}
_clients_lock = threading.Lock()
_rotation_lock = threading.Lock()
_rotation_index = 0


def _default_headers() -> dict[str, str]:
    """Headers for ngrok compatibility and OpenRouter attribution."""
    return {
        **NGROK_HEADERS,
        "HTTP-Referer": "https://github.com/TranQuangMinh-2005/RedLine",
        "X-Title": "RedLine Target",
    }


def _provider_specs() -> list[ProviderSpec]:
    settings = get_settings()
    primary = llm_runtime.get_active()
    providers = [
        ProviderSpec(
            slot="primary",
            name=primary.provider,
            model=primary.model,
            api_key=primary.api_key,
            base_url=primary.base_url,
        )
    ]
    secondary_configured = bool(
        settings.LLM_SECONDARY_API_KEY.strip() or settings.LLM_SECONDARY_BASE_URL.strip()
    )
    if secondary_configured:
        providers.append(
            ProviderSpec(
                slot="secondary",
                name=settings.LLM_SECONDARY_PROVIDER.strip() or "secondary",
                model=settings.LLM_SECONDARY_MODEL.strip() or primary.model,
                api_key=settings.LLM_SECONDARY_API_KEY.strip(),
                base_url=settings.LLM_SECONDARY_BASE_URL.strip() or primary.base_url,
            )
        )
    return providers


def _get_client(provider: ProviderSpec) -> OpenAI:
    settings = get_settings()
    api_key = provider.api_key or "ollama"
    cache_key = (provider.slot, provider.base_url, api_key)
    with _clients_lock:
        client = _clients.get(cache_key)
        if client is None:
            client = OpenAI(
                api_key=api_key,
                base_url=provider.base_url,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                max_retries=2,
                default_headers=_default_headers(),
            )
            _clients[cache_key] = client
        return client


def get_client() -> OpenAI:
    """Return the client for the active primary runtime endpoint."""
    return _get_client(_provider_specs()[0])


def _ordered_attempts(providers: list[ProviderSpec], mode: str) -> list[ProviderSpec]:
    global _rotation_index
    if len(providers) == 1 or mode == "primary":
        return providers[:1]
    if mode == "failover":
        return providers
    with _rotation_lock:
        selected = _rotation_index % len(providers)
        _rotation_index += 1
    return providers[selected:] + providers[:selected]


def _reset_routing_state() -> None:
    """Reset client cache and round-robin cursor for deterministic tests."""
    global _rotation_index
    with _clients_lock:
        _clients.clear()
    with _rotation_lock:
        _rotation_index = 0


def chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = 1024,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
) -> dict[str, Any]:
    """Send one completion through the configured primary/secondary routing policy."""
    settings = get_settings()
    attempts = _ordered_attempts(_provider_specs(), settings.LLM_ROUTING_MODE)
    started = time.time()
    attempted_slots: list[str] = []
    response = None
    selected_provider = attempts[0]
    last_error: Exception | None = None

    for provider in attempts:
        attempted_slots.append(provider.slot)
        request: dict[str, Any] = {
            "model": model or provider.model,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = tool_choice or "auto"
        reasoning_effort = getattr(settings, "LLM_REASONING_EFFORT", "")
        if reasoning_effort:
            request["reasoning_effort"] = reasoning_effort
        try:
            response = _get_client(provider).chat.completions.create(**request)
            selected_provider = provider
            break
        except Exception as exc:
            last_error = exc

    if response is None:
        assert last_error is not None
        raise last_error

    latency = time.time() - started
    choice = response.choices[0]
    tool_calls = [
        {
            "id": call.id or f"call_{index}",
            "type": "function",
            "function": {"name": call.function.name, "arguments": call.function.arguments},
        }
        for index, call in enumerate(choice.message.tool_calls or [])
    ]
    text, reasoning = split_reasoning(choice.message.content or "", choice.message)
    return {
        "text": text,
        "reasoning": reasoning,
        "model": response.model,
        "provider": selected_provider.name,
        "provider_slot": selected_provider.slot,
        "provider_attempts": attempted_slots,
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        "total_tokens": response.usage.total_tokens if response.usage else 0,
        "latency_s": round(latency, 3),
        "finish_reason": choice.finish_reason,
        "tool_calls": tool_calls,
    }


def summarize_error(exc: Exception) -> str:
    """Return a safe error label without leaking endpoint credentials."""
    return type(exc).__name__
