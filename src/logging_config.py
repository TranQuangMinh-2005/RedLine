"""JSON structured audit logging for reconstructing target runs."""

from __future__ import annotations

import hashlib
import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from src.config import get_settings
from src.services.redact import redact

LOGGER_NAME = "redline.audit"
_request_context: ContextVar[tuple[str, str | None] | None] = ContextVar("redline_request", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "event_payload", {"event": record.getMessage()})
        return json.dumps(redact(payload), ensure_ascii=False, sort_keys=True, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, get_settings().LOG_LEVEL.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def audit_event(event: str, *, request_id: str, session_id: str | None = None, **fields: Any) -> None:
    settings = get_settings()
    # Đọc profile từ runtime state (có thể đổi qua API) thay vì .env tĩnh,
    # nếu không log sẽ ghi sai mode khi guardrail được chuyển giữa các run.
    try:
        from src.guardrails import state as defense_state

        active_profile = defense_state.get_active_name()
    except Exception:  # noqa: BLE001 — logging không được làm sập request
        active_profile = settings.DEFENSE_PROFILE

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "request_id": request_id,
        "session_id_hash": session_hash(session_id) if session_id else None,
        "defense_profile": active_profile,
        "target_config_hash": settings.target_config_hash,
        **fields,
    }
    logger = configure_logging()
    logger.info(event, extra={"event_payload": payload})


def set_request_context(request_id: str, session_id: str | None) -> Token:
    return _request_context.set((request_id, session_id))


def reset_request_context(token: Token) -> None:
    _request_context.reset(token)


def current_audit_event(event: str, **fields: Any) -> None:
    context = _request_context.get()
    if context:
        audit_event(event, request_id=context[0], session_id=context[1], **fields)
