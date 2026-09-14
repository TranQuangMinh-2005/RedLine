"""Output-side guardrail and canary leak prevention."""

from __future__ import annotations

import re
from dataclasses import dataclass

from guardrails.profiles import DefenseProfile

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


@dataclass(frozen=True)
class OutputDecision:
    text: str
    filtered: bool
    actions: tuple[str, ...] = ()


def _contains_canary(text: str, canary: str) -> bool:
    if not canary or canary == "CANARY-REDLINE-REPLACE-ME":
        return False
    normalized_text = re.sub(r"\s+", "", text).casefold()
    normalized_canary = re.sub(r"\s+", "", canary).casefold()
    return normalized_canary in normalized_text


def inspect_output(
    text: str,
    profile: DefenseProfile,
    *,
    canary: str,
) -> OutputDecision:
    """Filter an LLM response before it is returned to the caller."""

    if profile.canary_check and _contains_canary(text, canary):
        return OutputDecision(
            text=BLOCKED_OUTPUT_REPLY,
            filtered=True,
            actions=("output_block:canary",),
        )

    if profile.output_filter:
        for rule_name, pattern in _SENSITIVE_OUTPUT_PATTERNS:
            if pattern.search(text):
                return OutputDecision(
                    text=BLOCKED_OUTPUT_REPLY,
                    filtered=True,
                    actions=(f"output_block:{rule_name}",),
                )

    return OutputDecision(text=text, filtered=False)
