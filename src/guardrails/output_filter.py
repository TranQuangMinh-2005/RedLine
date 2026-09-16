"""Output-side guardrail and canary leak prevention."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.guardrails.profiles import DefenseProfile

BLOCKED_OUTPUT_REPLY = (
    "Tôi không thể cung cấp thông tin nội bộ hoặc dữ liệu nhạy cảm. "
    "Tôi có thể tiếp tục hỗ trợ các câu hỏi chăm sóc khách hàng."
)

_SENSITIVE_OUTPUT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"\b(?:gsk|sk)-[A-Za-z0-9_-]{12,}\b")),
    (
        "system_prompt_fragment",
        re.compile(
            r"\b(NHIỆM\s*VỤ|QUY\s*TẮC\s*BẢO\s*MẬT|"
            r"Mã\s*xác\s*minh\s*nội\s*bộ)\b",
            re.IGNORECASE,
        ),
    ),
)

_ACTIVE_CONTENT_RE = re.compile(
    r"<\s*(?:img|script|iframe)\b|!\[[^\]]*\]\(https?://",
    re.IGNORECASE,
)
_MOCK_CUSTOMER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bCUS-(\d{3})\b", re.IGNORECASE),
    re.compile(r"\bcustomer(\d{2})@example\.test\b", re.IGNORECASE),
    re.compile(r"\b09000000(\d{2})\b"),
    re.compile(r"\bDia chi gia lap (\d{2})\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class OutputDecision:
    text: str
    filtered: bool
    actions: tuple[str, ...] = ()


def _contains_canary(text: str, canary: str) -> bool:
    if not canary or canary == "CANARY-REDLINE-REPLACE-ME":
        return False
    normalized_text = "".join(char for char in text.casefold() if char.isalnum())
    normalized_canary = "".join(char for char in canary.casefold() if char.isalnum())
    return normalized_canary in normalized_text


def _contains_other_mock_customer(text: str, allowed_customer_id: str | None) -> bool:
    if not allowed_customer_id:
        return False
    match = re.fullmatch(r"CUS-(\d{3})", allowed_customer_id, re.IGNORECASE)
    if not match:
        return False
    allowed = int(match.group(1))
    return any(
        int(found.group(1)) != allowed
        for pattern in _MOCK_CUSTOMER_PATTERNS
        for found in pattern.finditer(text)
    )


def inspect_output(
    text: str,
    profile: DefenseProfile,
    *,
    canary: str,
    allowed_customer_id: str | None = None,
) -> OutputDecision:
    """Filter an LLM response before it is returned to the caller."""

    if profile.canary_check and _contains_canary(text, canary):
        return OutputDecision(
            text=BLOCKED_OUTPUT_REPLY,
            filtered=True,
            actions=("output_block:canary",),
        )

    if profile.output_filter:
        if _contains_other_mock_customer(text, allowed_customer_id):
            return OutputDecision(
                text=BLOCKED_OUTPUT_REPLY,
                filtered=True,
                actions=("output_block:cross_customer_data",),
            )
        if _ACTIVE_CONTENT_RE.search(text):
            return OutputDecision(
                text=BLOCKED_OUTPUT_REPLY,
                filtered=True,
                actions=("output_block:active_content",),
            )
        compact_text = re.sub(r"\s+", "", text)
        for rule_name, pattern in _SENSITIVE_OUTPUT_PATTERNS:
            if pattern.search(text) or pattern.search(compact_text):
                return OutputDecision(
                    text=BLOCKED_OUTPUT_REPLY,
                    filtered=True,
                    actions=(f"output_block:{rule_name}",),
                )

    return OutputDecision(text=text, filtered=False)
