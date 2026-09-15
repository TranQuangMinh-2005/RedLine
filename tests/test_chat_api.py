from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.agents.state_store import InMemorySessionStore
from src.api.routers import chat as chat_router
from src.main import app


def _agent_result(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "model": "mock-model",
        "prompt_tokens": 4,
        "completion_tokens": 3,
        "total_tokens": 7,
        "latency_s": 0.001,
        "finish_reason": "stop",
        "tool_calls": [],
    }


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(chat_router, "session_store", InMemorySessionStore(max_messages=50))
    return TestClient(app)


def test_health_is_fast_and_does_not_call_the_llm(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router.target_agent, "respond", lambda *_args, **_kwargs: pytest.fail("LLM called"))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_creates_a_session_and_returns_the_stable_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router.target_agent, "respond", lambda *_args, **_kwargs: _agent_result("Xin chÃ o"))
    response = client.post("/chat", json={"message": "Xin chao"})

    assert response.status_code == 200
    payload = response.json()
    UUID(payload["session_id"])
    assert payload["reply"] == "Xin chÃ o"
    assert payload["model"] == "mock-model"
    assert payload["total_tokens"] == 7
    assert set(payload) == {
        "session_id",
        "reply",
        "model",
        "latency_s",
        "total_tokens",
        "canary_leaked",
        "defense_profile",
        "target_config_hash",
        "guardrail_blocked",
        "guardrail_actions",
    }


def test_chat_passes_complete_history_on_turn_two(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[dict[str, str]]] = []

    def fake_respond(messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        captured.append(messages)
        return _agent_result(f"answer-{len(captured)}")

    monkeypatch.setattr(chat_router.target_agent, "respond", fake_respond)
    first = client.post("/chat", json={"message": "Ma don cua toi la ORD-001"})
    session_id = first.json()["session_id"]
    second = client.post("/chat", json={"message": "Don do dang o dau?", "session_id": session_id})

    assert second.status_code == 200
    assert second.json()["session_id"] == session_id
    assert captured[0] == [{"role": "user", "content": "Ma don cua toi la ORD-001"}]
    assert captured[1] == [
        {"role": "user", "content": "Ma don cua toi la ORD-001"},
        {"role": "assistant", "content": "answer-1"},
        {"role": "user", "content": "Don do dang o dau?"},
    ]


def test_chat_does_not_leak_history_across_sessions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[dict[str, str]]] = []

    def fake_respond(messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        captured.append(messages)
        return _agent_result("ok")

    monkeypatch.setattr(chat_router.target_agent, "respond", fake_respond)
    client.post("/chat", json={"message": "private ORD-001", "session_id": "session-a"})
    client.post("/chat", json={"message": "What order?", "session_id": "session-b"})

    assert captured[1] == [{"role": "user", "content": "What order?"}]
    assert "ORD-001" not in str(captured[1])


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "x" * 4001},
        {"message": "valid", "session_id": "contains spaces"},
        {"message": "valid", "session_id": "x" * 101},
    ],
)
def test_chat_rejects_invalid_request_schema(client: TestClient, body: dict[str, str]) -> None:
    response = client.post("/chat", json=body)
    assert response.status_code == 422


def test_client_model_override_is_ignored_and_never_forwarded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: list[dict[str, Any]] = []

    def fake_respond(_messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        captured_kwargs.append(kwargs)
        return _agent_result("ok")

    monkeypatch.setattr(chat_router.target_agent, "respond", fake_respond)
    response = client.post("/chat", json={"message": "hello", "model": "attacker-controlled-model"})

    assert response.status_code == 200
    assert response.json()["model"] == "mock-model"
    assert "model" not in captured_kwargs[0]


def test_provider_failure_returns_a_sanitized_502(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "gsk-secret-that-must-not-leak"

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(f"provider failed with {secret}")

    monkeypatch.setattr(chat_router.target_agent, "respond", fail)
    monkeypatch.setattr(chat_router.target_agent.llm, "summarize_error", lambda exc: type(exc).__name__)
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM error: RuntimeError"
    assert secret not in response.text


def test_kill_switch_returns_503_before_calling_the_agent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = chat_router.get_settings()
    monkeypatch.setattr(settings, "ROE_KILL_SWITCH", True)
    monkeypatch.setattr(chat_router.target_agent, "respond", lambda *_args, **_kwargs: pytest.fail("agent called"))
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 503


def test_session_limit_returns_429(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_router, "session_store", InMemorySessionStore(max_messages=2))
    monkeypatch.setattr(chat_router.target_agent, "respond", lambda *_args, **_kwargs: _agent_result("ok"))

    first = client.post("/chat", json={"message": "turn one", "session_id": "limited"})
    second = client.post("/chat", json={"message": "turn two", "session_id": "limited"})

    assert first.status_code == 200
    assert second.status_code == 429
