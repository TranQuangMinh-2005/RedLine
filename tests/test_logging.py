from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from src import logging_config
from src.services import redact as redact_module


def test_redact_removes_secrets_and_nested_mock_pii(sensitive_settings: SimpleNamespace) -> None:
    value = {
        "authorization": "Bearer should-never-appear",
        "nested": {
            "api_key": sensitive_settings.LLM_API_KEY,
            "canary_token": sensitive_settings.CANARY_TOKEN,
            "email": "customer01@example.test",
            "phone": "0900000001",
            "address": "Mock address 01",
        },
        "free_text": (
            f"key={sensitive_settings.LLM_API_KEY} canary={sensitive_settings.CANARY_TOKEN} "
            "email=customer01@example.test phone=0900000001 Bearer abc.def.ghi"
        ),
    }

    redacted = redact_module.redact(value)
    serialized = json.dumps(redacted)

    for forbidden in (
        "should-never-appear",
        sensitive_settings.LLM_API_KEY,
        sensitive_settings.CANARY_TOKEN,
        "customer01@example.test",
        "0900000001",
        "Mock address 01",
        "abc.def.ghi",
    ):
        assert forbidden not in serialized
    assert serialized.count(redact_module.REDACTED) >= 7


def test_json_formatter_emits_parseable_redacted_json(sensitive_settings: SimpleNamespace) -> None:
    record = logging.LogRecord(
        name="redline.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="tool_completed",
        args=(),
        exc_info=None,
    )
    record.event_payload = {
        "timestamp": "2026-09-15T00:00:00+00:00",
        "event": "tool_completed",
        "request_id": "REQ-001",
        "session_id_hash": "abc123",
        "email": "customer01@example.test",
    }

    payload = json.loads(logging_config.JsonFormatter().format(record))

    assert payload["event"] == "tool_completed"
    assert payload["request_id"] == "REQ-001"
    assert payload["session_id_hash"] == "abc123"
    assert payload["email"] == redact_module.REDACTED


def test_audit_event_has_fields_needed_to_correlate_a_run(
    monkeypatch: pytest.MonkeyPatch,
    sensitive_settings: SimpleNamespace,
) -> None:
    captured: list[dict[str, object]] = []

    class CapturingLogger:
        def info(self, _message: str, *, extra: dict[str, object]) -> None:
            captured.append(extra["event_payload"])  # type: ignore[arg-type]

    monkeypatch.setattr(logging_config, "configure_logging", lambda: CapturingLogger())

    logging_config.audit_event(
        "retrieval_completed",
        request_id="REQ-001",
        session_id="SESSION-PRIVATE",
        document_ids=["shipping-policy"],
        result_count=1,
    )

    assert len(captured) == 1
    event = captured[0]
    assert event["timestamp"]
    assert event["event"] == "retrieval_completed"
    assert event["request_id"] == "REQ-001"
    assert event["session_id_hash"] == logging_config.session_hash("SESSION-PRIVATE")
    assert event["defense_profile"] == "none"
    assert event["target_config_hash"] == "config123"
    assert event["document_ids"] == ["shipping-policy"]
    assert "session_id" not in event


def test_request_context_correlates_nested_agent_events(
    monkeypatch: pytest.MonkeyPatch,
    sensitive_settings: SimpleNamespace,
) -> None:
    captured: list[dict[str, object]] = []

    class CapturingLogger:
        def info(self, _message: str, *, extra: dict[str, object]) -> None:
            captured.append(extra["event_payload"])  # type: ignore[arg-type]

    monkeypatch.setattr(logging_config, "configure_logging", lambda: CapturingLogger())
    token = logging_config.set_request_context("REQ-NESTED", "SESSION-NESTED")
    try:
        logging_config.current_audit_event("tool_called", tool_name="get_ticket", tool_call_id="call-1")
        logging_config.current_audit_event("tool_completed", tool_name="get_ticket", tool_call_id="call-1")
    finally:
        logging_config.reset_request_context(token)

    assert [event["event"] for event in captured] == ["tool_called", "tool_completed"]
    assert {event["request_id"] for event in captured} == {"REQ-NESTED"}
    assert {event["session_id_hash"] for event in captured} == {
        logging_config.session_hash("SESSION-NESTED")
    }
