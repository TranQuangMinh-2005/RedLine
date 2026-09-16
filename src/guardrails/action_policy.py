"""Deterministic policy checks for LLM-proposed tool calls.

The model may propose an action, but this module decides whether the action is
allowed.  It deliberately contains no LLM call so authorization remains
auditable and cannot be changed by prompt injection.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.guardrails.profiles import DefenseProfile

_STRICT_TOOL_LIMITS = {
    "search_knowledge": 2,
    "get_customer_info": 1,
    "get_ticket": 2,
    "create_ticket": 1,
}

_CREATE_TICKET_INTENT = re.compile(
    r"\b(create|open|submit|tao|mo|lap|gui)\b.{0,40}"
    r"\b(ticket|support request|yeu cau ho tro)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    arguments: dict[str, Any]
    status: str = "allowed"
    actions: tuple[str, ...] = ()
    error: str | None = None


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).casefold()
    return "".join(char for char in normalized if not unicodedata.combining(char))


def inspect_tool_call(
    name: str,
    arguments: dict[str, Any],
    profile: DefenseProfile,
    *,
    allowed_customer_id: str,
    latest_user_message: str,
    call_count: int,
    server_request_id: str | None = None,
) -> ActionDecision:
    """Validate a proposed tool call before dispatching it to the tool layer."""

    safe_arguments = dict(arguments)

    if profile.tool_authorization and name in {"get_customer_info", "create_ticket"}:
        requested_customer = safe_arguments.get("customer_id")
        if requested_customer != allowed_customer_id:
            return ActionDecision(
                allowed=False,
                arguments=safe_arguments,
                status="forbidden",
                actions=("tool_block:customer_scope",),
                error="customer access is not authorized",
            )

    # Idempotency is server-owned for protected profiles; the model cannot
    # choose a key that aliases another user's or another request's action.
    if profile.tool_authorization and name == "create_ticket" and server_request_id:
        safe_arguments["request_id"] = server_request_id

    if not profile.action_policy:
        return ActionDecision(allowed=True, arguments=safe_arguments)

    limit = _STRICT_TOOL_LIMITS.get(name, 0)
    if limit == 0:
        return ActionDecision(
            allowed=False,
            arguments=safe_arguments,
            status="invalid_tool",
            actions=("tool_block:not_allowlisted",),
            error="tool is not permitted by the strict action policy",
        )
    if call_count > limit:
        return ActionDecision(
            allowed=False,
            arguments=safe_arguments,
            status="tool_limit",
            actions=("tool_block:per_tool_limit",),
            error="per-tool call limit reached",
        )

    if name == "create_ticket" and not _CREATE_TICKET_INTENT.search(
        _ascii_fold(latest_user_message)
    ):
        return ActionDecision(
            allowed=False,
            arguments=safe_arguments,
            status="confirmation_required",
            actions=("tool_hold:create_ticket_intent",),
            error="an explicit create-ticket request is required",
        )

    return ActionDecision(allowed=True, arguments=safe_arguments)
