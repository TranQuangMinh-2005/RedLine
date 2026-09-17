"""Output-side guardrail and canary leak prevention."""

from __future__ import annotations

import base64
import binascii
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
_ENCODED_TOKEN_RE = re.compile(r"\b(?:[A-Za-z0-9+/]{16,}={0,2}|[0-9a-fA-F]{24,})\b")


@dataclass(frozen=True)
class OutputDecision:
    text: str
    filtered: bool
    actions: tuple[str, ...] = ()
    # Đoạn khớp luật (canary luôn được thay bằng [CANARY]) — chỉ dùng cho trace/UI.
    matched_text: str | None = None


def _contains_canary(text: str, canary: str) -> bool:
    if not canary or canary == "CANARY-REDLINE-REPLACE-ME":
        return False
    normalized_text = "".join(char for char in text.casefold() if char.isalnum())
    normalized_canary = "".join(char for char in canary.casefold() if char.isalnum())
    return normalized_canary in normalized_text


def _other_mock_customer_match(text: str, allowed_customer_id: str | None) -> str | None:
    """Trả chuỗi dữ liệu mock của khách hàng KHÁC nếu có trong text."""
    if not allowed_customer_id:
        return None
    match = re.fullmatch(r"CUS-(\d{3})", allowed_customer_id, re.IGNORECASE)
    if not match:
        return None
    allowed = int(match.group(1))
    return next(
        (
            found.group(0)
            for pattern in _MOCK_CUSTOMER_PATTERNS
            for found in pattern.finditer(text)
            if int(found.group(1)) != allowed
        ),
        None,
    )



def _decoded_candidates(text: str) -> tuple[str, ...]:
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
            if candidate:
                decoded.append(candidate)
    return tuple(decoded)


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
            matched_text="[CANARY]",
        )

    if profile.output_filter:
        if any(_contains_canary(candidate, canary) for candidate in _decoded_candidates(text)):
            return OutputDecision(
                text=BLOCKED_OUTPUT_REPLY,
                filtered=True,
                actions=("output_block:encoded_canary",),
                matched_text="[CANARY đã mã hóa]",
            )
        other_customer = _other_mock_customer_match(text, allowed_customer_id)
        if other_customer:
            return OutputDecision(
                text=BLOCKED_OUTPUT_REPLY,
                filtered=True,
                actions=("output_block:cross_customer_data",),
                matched_text=other_customer,
            )
        active = _ACTIVE_CONTENT_RE.search(text)
        if active:
            return OutputDecision(
                text=BLOCKED_OUTPUT_REPLY,
                filtered=True,
                actions=("output_block:active_content",),
                matched_text=active.group(0)[:200],
            )
        compact_text = re.sub(r"\s+", "", text)
        for rule_name, pattern in _SENSITIVE_OUTPUT_PATTERNS:
            match = pattern.search(text) or pattern.search(compact_text)
            if match:
                return OutputDecision(
                    text=BLOCKED_OUTPUT_REPLY,
                    filtered=True,
                    actions=(f"output_block:{rule_name}",),
                    matched_text=match.group(0)[:200],
                )

    return OutputDecision(text=text, filtered=False)
