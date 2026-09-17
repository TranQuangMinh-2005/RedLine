"""Code-level trust boundary for content returned by the RAG tool."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.guardrails.profiles import DefenseProfile

_RAG_INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|bo\s*qua|quen)\b.{0,80}"
            r"\b(previous|prior|above|instructions?|rules?|chi\s*thi|quy\s*tac)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "authority_marker",
        re.compile(
            r"(?:^|\n)\s*(system|developer|assistant|instruction)\s*:",
            re.IGNORECASE,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"\b(you\s+are\s+now|act\s+as|developer\s+mode|dan|dong\s+vai)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(reveal|print|send|exfiltrate|tiet\s*lo|in\s+ra)\b.{0,80}"
            r"\b(secret|system\s*prompt|canary|api\s*key|bi\s*mat)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


@dataclass(frozen=True)
class RagDecision:
    result: dict[str, Any]
    blocked: bool
    actions: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).casefold()
    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char) and unicodedata.category(char) != "Cf"
    )


def _find_rule(text: str) -> str | None:
    normalized = _normalize(text)
    for rule_name, pattern in _RAG_INJECTION_RULES:
        if pattern.search(normalized):
            return rule_name
    return None


def inspect_rag_result(result: dict[str, Any], profile: DefenseProfile) -> RagDecision:
    """Annotate retrieved rows and, in strict mode, quarantine suspicious rows."""

    rows = result.get("data")
    if not isinstance(rows, list) or not profile.prompt_hardening:
        return RagDecision(result=result, blocked=False)

    safe_rows: list[Any] = []
    actions: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            if not profile.rag_filter:
                safe_rows.append(row)
            continue

        protected_row = dict(row)
        protected_row["trust_level"] = "untrusted_retrieved_data"
        rule = _find_rule(str(row.get("text") or ""))
        if profile.rag_filter and rule:
            actions.append(f"rag_drop:{rule}")
            continue
        safe_rows.append(protected_row)

    protected_result = dict(result)
    protected_result["data"] = safe_rows
    if actions and not safe_rows:
        protected_result.update(
            ok=False,
            status="blocked",
            error="retrieved content failed the strict RAG security policy",
        )
    elif actions:
        protected_result["status"] = "partial"

    return RagDecision(
        result=protected_result,
        blocked=bool(actions),
        actions=tuple(dict.fromkeys(actions)),
    )
