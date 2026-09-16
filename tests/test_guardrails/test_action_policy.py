from src.guardrails.action_policy import inspect_tool_call
from src.guardrails.profiles import get_defense_profile


def test_none_keeps_intentionally_weak_baseline_customer_scope() -> None:
    decision = inspect_tool_call(
        "get_customer_info",
        {"customer_id": "CUS-002"},
        get_defense_profile("none"),
        allowed_customer_id="CUS-001",
        latest_user_message="show CUS-002",
        call_count=1,
    )
    assert decision.allowed is True


def test_basic_enforces_customer_scope_in_code() -> None:
    decision = inspect_tool_call(
        "get_customer_info",
        {"customer_id": "CUS-002"},
        get_defense_profile("basic"),
        allowed_customer_id="CUS-001",
        latest_user_message="show CUS-002",
        call_count=1,
    )
    assert decision.allowed is False
    assert decision.actions == ("tool_block:customer_scope",)


def test_strict_requires_explicit_write_intent_and_limits_repeated_calls() -> None:
    profile = get_defense_profile("strict")
    held = inspect_tool_call(
        "create_ticket",
        {"customer_id": "CUS-001", "subject": "x", "description": "y"},
        profile,
        allowed_customer_id="CUS-001",
        latest_user_message="Cho tôi biết chính sách hoàn tiền",
        call_count=1,
        server_request_id="req-1",
    )
    repeated = inspect_tool_call(
        "create_ticket",
        {"customer_id": "CUS-001", "subject": "x", "description": "y"},
        profile,
        allowed_customer_id="CUS-001",
        latest_user_message="Tạo ticket giúp tôi",
        call_count=2,
        server_request_id="req-1",
    )

    assert held.allowed is False
    assert held.status == "confirmation_required"
    assert repeated.allowed is False
    assert repeated.actions == ("tool_block:per_tool_limit",)


def test_protected_profile_binds_idempotency_to_server_request() -> None:
    decision = inspect_tool_call(
        "create_ticket",
        {
            "customer_id": "CUS-001",
            "subject": "x",
            "description": "y",
            "request_id": "model-controlled",
        },
        get_defense_profile("basic"),
        allowed_customer_id="CUS-001",
        latest_user_message="Tạo ticket giúp tôi",
        call_count=1,
        server_request_id="server-controlled",
    )
    assert decision.allowed is True
    assert decision.arguments["request_id"] == "server-controlled"
