from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.services import llm


class FakeCompletions:
    def __init__(self, name: str, calls: list[str], *, fail: bool = False) -> None:
        self.name = name
        self.calls = calls
        self.fail = fail

    def create(self, **request: Any) -> SimpleNamespace:
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} unavailable")
        message = SimpleNamespace(content=f"from-{self.name}", tool_calls=[])
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)
        return SimpleNamespace(model=request["model"], choices=[choice], usage=usage)


def _settings(mode: str = "round_robin", *, secondary: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        LLM_PROVIDER="groq-primary",
        LLM_MODEL="primary-model",
        LLM_API_KEY="primary-key",
        LLM_BASE_URL="https://primary.example/v1",
        LLM_TEMPERATURE=0.0,
        LLM_REASONING_EFFORT="",
        LLM_ROUTING_MODE=mode,
        LLM_SECONDARY_PROVIDER="groq-secondary",
        LLM_SECONDARY_MODEL="secondary-model",
        LLM_SECONDARY_API_KEY="secondary-key" if secondary else "",
        LLM_SECONDARY_BASE_URL="https://secondary.example/v1" if secondary else "",
    )


@pytest.fixture(autouse=True)
def reset_routing() -> None:
    llm._reset_routing_state()


def _install_clients(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    primary_fails: bool = False,
    secondary_fails: bool = False,
) -> None:
    settings = llm.get_settings()
    monkeypatch.setattr(
        llm.llm_runtime,
        "get_active",
        lambda: SimpleNamespace(
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        ),
    )
    clients = {
        "primary": SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions("primary", calls, fail=primary_fails))
        ),
        "secondary": SimpleNamespace(
            chat=SimpleNamespace(
                completions=FakeCompletions("secondary", calls, fail=secondary_fails)
            )
        ),
    }
    monkeypatch.setattr(llm, "_get_client", lambda provider: clients[provider.slot])


def test_round_robin_alternates_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    _install_clients(monkeypatch, calls)

    first = llm.chat([{"role": "user", "content": "one"}])
    second = llm.chat([{"role": "user", "content": "two"}])

    assert calls == ["primary", "secondary"]
    assert first["provider_slot"] == "primary"
    assert first["model"] == "primary-model"
    assert second["provider_slot"] == "secondary"
    assert second["model"] == "secondary-model"


def test_round_robin_fails_over_to_other_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    _install_clients(monkeypatch, calls, primary_fails=True)

    result = llm.chat([{"role": "user", "content": "hello"}])

    assert calls == ["primary", "secondary"]
    assert result["provider_slot"] == "secondary"
    assert result["provider_attempts"] == ["primary", "secondary"]


def test_failover_mode_prefers_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("failover"))
    _install_clients(monkeypatch, calls)

    llm.chat([{"role": "user", "content": "one"}])
    llm.chat([{"role": "user", "content": "two"}])

    assert calls == ["primary", "primary"]


def test_missing_secondary_gracefully_uses_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(secondary=False))
    _install_clients(monkeypatch, calls)

    result = llm.chat([{"role": "user", "content": "hello"}])

    assert calls == ["primary"]
    assert result["provider_attempts"] == ["primary"]
