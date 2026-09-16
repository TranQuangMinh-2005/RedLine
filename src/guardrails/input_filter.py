"""Input-side guardrail for direct prompt-injection attempts."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

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
    (
        "obfuscated_instruction_override",
        re.compile(
            r"\bi[\W_]*g[\W_]*n[\W_]*o[\W_]*r[\W_]*e\b.{0,80}"
            r"\b(previous|prior|instructions?|rules?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "implicit_prompt_extraction",
        re.compile(
            r"\b(exact|verbatim|word[- ]for[- ]word)\b.{0,50}"
            r"\b(text|words?|content)\b.{0,50}"
            r"\b(initiali[sz]ed|configured|governs?|controls?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


@dataclass(frozen=True)
class InputDecision:
    blocked: bool
    actions: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    # Format controls such as zero-width joiners are a common regex bypass.
    return "".join(char for char in normalized if unicodedata.category(char) != "Cf")


_ENCODED_TOKEN_RE = re.compile(r"\b(?:[A-Za-z0-9+/]{16,}={0,2}|[0-9a-fA-F]{24,})\b")


def _decoded_candidates(text: str) -> tuple[str, ...]:
    """Best-effort decode of standalone Base64/hex payloads for strict inspection."""
    decoded: list[str] = []
    for token in _ENCODED_TOKEN_RE.findall(text):
        attempts: list[bytes] = []
        try:
            attempts.append(base64.b64decode(token + "=" * (-len(token) % 4), validate=True))
        except (ValueError, binascii.Error):
            pass
        if len(token) % 2 == 0:
            try:
                attempts.append(bytes.fromhex(token))
            except ValueError:
                pass
        for raw in attempts:
            try:
                candidate = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if candidate and sum(char.isprintable() for char in candidate) / len(candidate) >= 0.9:
                decoded.append(candidate)
    return tuple(decoded)


def inspect_input(text: str, profile: DefenseProfile) -> InputDecision:
    """Inspect one user message according to the selected profile."""

    if not profile.input_filter:
        return InputDecision(blocked=False)

    candidates = [_normalize(text)]
    if profile.name == "strict":
        candidates.extend(_normalize(candidate) for candidate in _decoded_candidates(text))
    rules = _BASIC_RULES + (_STRICT_RULES if profile.name == "strict" else ())
    for candidate in candidates:
        for rule_name, pattern in rules:
            if pattern.search(candidate):
                return InputDecision(blocked=True, actions=(f"input_block:{rule_name}",))
    return InputDecision(blocked=False)


def inspect_messages(messages: list[dict[str, Any]], profile: DefenseProfile) -> InputDecision:
    """Inspect every user turn so an older poisoned turn cannot bypass the current mode."""
    for message in messages:
        if message.get("role") != "user":
            continue
        decision = inspect_input(str(message.get("content") or ""), profile)
        if decision.blocked:
            return decision
    return InputDecision(blocked=False)
