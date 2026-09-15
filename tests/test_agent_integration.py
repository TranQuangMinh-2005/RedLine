from __future__ import annotations

import json
from typing import Any

import pytest

from src.agent import target_agent


def _llm_result(*, text: str = "", tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "text": text,
        "model": "mock-model",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_s": 0.01,
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "tool_calls": tool_calls or [],
    }


def _tool_call(name: str, arguments: object, call_id: str = "call-1") -> dict[str, Any]:
    encoded = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": encoded}}


def test_agent_returns_direct_response_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    def fake_chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        captured.extend(messages)
        assert kwargs["tools"]
        return _llm_result(text="Xin chÃ o!")

    monkeypatch.setattr(target_agent.llm, "chat", fake_chat)
    result = target_agent.respond([{"role": "user", "content": "Xin chÃ o"}])

    assert result["text"] == "Xin chÃ o!"
    assert captured[0]["role"] == "system"
    assert captured[-1] == {"role": "user", "content": "Xin chÃ o"}


@pytest.mark.parametrize("tool_name", ["search_knowledge", "get_customer_info", "get_ticket", "create_ticket"])
def test_agent_executes_each_allowlisted_tool_and_returns_result_to_llm(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    calls = [
        _llm_result(tool_calls=[_tool_call(tool_name, {"test": "value"})]),
        _llm_result(text="Káº¿t quáº£ cuá»‘i."),
    ]
    llm_messages: list[list[dict[str, Any]]] = []
    executed: list[tuple[str, dict[str, Any]]] = []

    def fake_chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        llm_messages.append(list(messages))
        return calls.pop(0)

    def fake_execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        executed.append((name, arguments))
        return {"ok": True, "status": "success", "data": {"evidence": "mock"}, "error": None}

    monkeypatch.setattr(target_agent.llm, "chat", fake_chat)
    monkeypatch.setattr(target_agent, "execute_tool", fake_execute)

    result = target_agent.respond([{"role": "user", "content": "Há»— trá»£ tÃ´i"}])

    assert result["text"] == "Káº¿t quáº£ cuá»‘i."
    assert executed == [(tool_name, {"test": "value"})]
    tool_messages = [message for message in llm_messages[1] if message["role"] == "tool"]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0]["content"])["data"] == {"evidence": "mock"}
    assert result["total_tokens"] == 30


def test_agent_handles_invalid_tool_json_without_executing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _llm_result(tool_calls=[_tool_call("get_ticket", "{invalid-json")]),
        _llm_result(text="KhÃ´ng thá»ƒ gá»i tool."),
    ]
    second_messages: list[dict[str, Any]] = []

    def fake_chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if len(responses) == 1:
            second_messages.extend(messages)
        return responses.pop(0)

    monkeypatch.setattr(target_agent.llm, "chat", fake_chat)
    monkeypatch.setattr(target_agent, "execute_tool", lambda *_: pytest.fail("invalid args must not execute"))

    result = target_agent.respond([{"role": "user", "content": "ticket"}])
    assert result["text"] == "KhÃ´ng thá»ƒ gá»i tool."
    tool_message = next(message for message in second_messages if message["role"] == "tool")
    assert json.loads(tool_message["content"])["status"] == "invalid_input"


def test_agent_stops_a_repeated_tool_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def fake_chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return _llm_result(tool_calls=[_tool_call("get_ticket", {"ticket_id": "TKT-001"}, f"call-{call_count}")])

    monkeypatch.setattr(target_agent.llm, "chat", fake_chat)
    monkeypatch.setattr(
        target_agent,
        "execute_tool",
        lambda *_: {"ok": True, "status": "success", "data": {}, "error": None},
    )

    result = target_agent.respond([{"role": "user", "content": "loop"}])

    assert 1 <= call_count <= 6
    assert result["finish_reason"] == "tool_limit"
    assert result["text"]


def test_agent_emits_reconstructable_retrieval_events(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _llm_result(tool_calls=[_tool_call("search_knowledge", {"query": "giao hang", "top_k": 1})]),
        _llm_result(text="Theo chÃ­nh sÃ¡ch váº­n chuyá»ƒn..."),
    ]
    events: list[tuple[str, dict[str, Any]]] = []

    monkeypatch.setattr(target_agent.llm, "chat", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr(
        target_agent,
        "execute_tool",
        lambda *_args, **_kwargs: {
            "ok": True,
            "status": "success",
            "data": [{"document_id": "shipping-policy", "text": "mock"}],
            "error": None,
        },
    )
    monkeypatch.setattr(
        target_agent,
        "current_audit_event",
        lambda event, **fields: events.append((event, fields)),
    )

    target_agent.respond([{"role": "user", "content": "giao hang"}])

    names = [name for name, _fields in events]
    assert names == [
        "llm_completed",
        "tool_called",
        "retrieval_started",
        "retrieval_completed",
        "tool_completed",
        "llm_completed",
    ]
    completed = next(fields for name, fields in events if name == "retrieval_completed")
    assert completed["result_count"] == 1
    assert completed["document_ids"] == ["shipping-policy"]


def test_agent_emits_tool_failed_when_execution_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _llm_result(tool_calls=[_tool_call("get_ticket", {"ticket_id": "TKT-404"})]),
        _llm_result(text="KhÃ´ng tÃ¬m tháº¥y ticket."),
    ]
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(target_agent.llm, "chat", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr(
        target_agent,
        "execute_tool",
        lambda *_args, **_kwargs: {"ok": False, "status": "not_found", "data": None, "error": "not found"},
    )
    monkeypatch.setattr(
        target_agent,
        "current_audit_event",
        lambda event, **fields: events.append((event, fields)),
    )

    target_agent.respond([{"role": "user", "content": "TKT-404"}])

    assert "tool_called" in [name for name, _fields in events]
    failed = next(fields for name, fields in events if name == "tool_failed")
    assert failed["tool_name"] == "get_ticket"
    assert failed["result_status"] == "not_found"
