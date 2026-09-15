"""Recursive secret and mock-PII redaction for logs."""

from __future__ import annotations

import re
from typing import Any

from src.config import get_settings

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {"authorization", "api_key", "llm_api_key", "canary", "canary_token", "email", "phone", "address", "shipping_address"}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?84|0)[\s.-]?\d(?:[\s.-]?\d){7,10}(?!\w)")
BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def redact(value: Any, *, key: str | None = None) -> Any:
    if key and key.casefold() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    result = value
    settings = get_settings()
    for secret in (settings.LLM_API_KEY, settings.CANARY_TOKEN):
        if secret and secret not in {"gsk-replace-me", "CANARY-REDLINE-REPLACE-ME"}:
            result = result.replace(secret, REDACTED)
    result = EMAIL_RE.sub(REDACTED, result)
    result = PHONE_RE.sub(REDACTED, result)
    return BEARER_RE.sub(f"Bearer {REDACTED}", result)
