from __future__ import annotations

from typing import Any
import pytest
from fastapi.testclient import TestClient

from src.agent import target_agent


def _mock_llm_result(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "model": "qwen2.5:14b",
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "latency_s": 0.05,
        "finish_reason": "stop",
        "tool_calls": [],
    }


def test_root_endpoint(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert "endpoints" in data


def test_models_endpoint(client: TestClient) -> None:
    for path in ["/v1/models", "/chat/v1/models", "/models"]:
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        model_ids = [m["id"] for m in data["data"]]
        assert "qwen2.5:14b" in model_ids


def test_chat_completions_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target_agent, "respond", lambda *args, **kwargs: _mock_llm_result("Xin chào! Tôi có thể giúp gì?"))

    for path in ["/v1/chat/completions", "/chat/v1/chat/completions"]:
        resp = client.post(
            path,
            json={
                "model": "qwen2.5:14b",
                "messages": [
                    {"role": "user", "content": "Chào bạn"},
                ],
                "stream": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Xin chào! Tôi có thể giúp gì?"
        assert data["usage"]["total_tokens"] == 20


def test_chat_completions_streaming(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target_agent, "respond", lambda *args, **kwargs: _mock_llm_result("Nội dung streaming"))

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:14b",
            "messages": [{"role": "user", "content": "Test stream"}],
            "stream": True,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text
    assert "data: [DONE]" in text
    assert "Nội dung streaming" in text
