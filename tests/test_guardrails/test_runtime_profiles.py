from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.routers import chat as chat_router


def _agent_result(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "model": "mock-model",
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "latency_s": 0.001,
        "finish_reason": "stop",
        "tool_calls": [],
    }


def test_runtime_switch_changes_effective_profile_and_config_hash(client: TestClient) -> None:
    none_health = client.get("/health").json()
    changed = client.post("/config/defense-profile", json={"profile": "strict"})
    strict_health = client.get("/health").json()

    assert changed.status_code == 200
    assert changed.json()["active"] == "strict"
    assert changed.json()["capabilities"]["tool_authorization"] is True
    assert strict_health["defense_profile"] == "strict"
    assert strict_health["scenario_customer_id"] == "CUS-001"
    assert strict_health["target_config_hash"] != none_health["target_config_hash"]


def test_strict_chat_blocks_cross_customer_output(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_router.target_agent,
        "respond",
        lambda *_args, **_kwargs: _agent_result("CUS-002 customer02@example.test"),
    )
    client.post("/config/defense-profile", json={"profile": "strict"})
    response = client.post("/chat", json={"message": "Thong tin tai khoan"})

    assert response.status_code == 200
    assert response.json()["guardrail_blocked"] is True
    assert response.json()["guardrail_actions"] == ["output_block:cross_customer_data"]
