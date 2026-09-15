"""Input-side guardrail for direct prompt-injection attempts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.guardrails.profiles import DefenseProfile

BLOCKED_INPUT_REPLY = (
    "Tôi không thể thực hiện yêu cầu thay đổi quy tắc hoặc tiết lộ thông tin nội bộ. "
    "Tôi có thể tiếp tục hỗ trợ các câu hỏi chăm sóc khách hàng."
)

_BASIC_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|bỏ\s*qua|quên)\b.{0,60}"
            r"\b(previous|prior|above|instructions?|rules?|chỉ\s*thị|quy\s*tắc)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "system_prompt_request",
        re.compile(
            r"\b(system\s*prompt|developer\s*(message|instruction)|"
            r"prompt\s*hệ\s*thống|chỉ\s*thị\s*(hệ\s*thống|nội\s*bộ))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "canary_request",
        re.compile(r"\b(canary|mã\s*xác\s*minh\s*nội\s*bộ)\b", re.IGNORECASE),
    ),
)

_STRICT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "role_override",
        re.compile(
            r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be|đóng\s+vai|"
            r"từ\s+giờ\s+bạn\s+là|developer\s+mode|DAN)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded_exfiltration",
        re.compile(
            r"\b(base64|rot13|hex|mã\s*hóa|encode|decode|dịch)\b.{0,80}"
            r"\b(prompt|instructions?|secret|canary|chỉ\s*thị|bí\s*mật)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "verbatim_instruction_request",
        re.compile(
            r"\b(repeat|print|reveal|show|output|nhắc\s*lại|in\s+ra|tiết\s*lộ)\b.{0,80}"
            r"\b(instructions?|rules?|prompt|secret|chỉ\s*thị|quy\s*tắc|bí\s*mật)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


@dataclass(frozen=True)
class InputDecision:
    blocked: bool
    actions: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def inspect_input(text: str, profile: DefenseProfile) -> InputDecision:
    """Inspect one user message according to the selected profile."""

    if not profile.input_filter:
        return InputDecision(blocked=False)

    normalized = _normalize(text)
    rules = _BASIC_RULES + (_STRICT_RULES if profile.name == "strict" else ())
    for rule_name, pattern in rules:
        if pattern.search(normalized):
            return InputDecision(blocked=True, actions=(f"input_block:{rule_name}",))
    return InputDecision(blocked=False)
