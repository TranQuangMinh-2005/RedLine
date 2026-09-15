"""Conversation state models + thread-safe session store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True)
class Message:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class SessionState:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionLimitError(RuntimeError):
    pass


class InMemorySessionStore:
    def __init__(self, max_messages: int = 50) -> None:
        if max_messages < 2:
            raise ValueError("max_messages must be at least 2")
        self.max_messages = max_messages
        self._sessions: dict[str, SessionState] = {}
        self._lock = RLock()

    def create_session(self, session_id: str | None = None) -> SessionState:
        with self._lock:
            identifier = session_id or str(uuid4())
            state = self._sessions.get(identifier)
            if state is None:
                state = SessionState(session_id=identifier)
                self._sessions[identifier] = state
            return self._copy(state)

    def get_session(self, session_id: str) -> SessionState | None:
        with self._lock:
            state = self._sessions.get(session_id)
            return self._copy(state) if state else None

    def append_message(self, session_id: str, role: str, content: str) -> SessionState:
        if role not in {"user", "assistant", "tool"}:
            raise ValueError("unsupported message role")
        with self._lock:
            state = self._sessions.setdefault(session_id, SessionState(session_id=session_id))
            if len(state.messages) >= self.max_messages:
                raise SessionLimitError("session message limit reached")
            state.messages.append(Message(role=role, content=content))
            state.updated_at = datetime.now(UTC)
            return self._copy(state)

    def clear_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _copy(self, state: SessionState) -> SessionState:
        return SessionState(
            session_id=state.session_id,
            messages=list(state.messages),
            created_at=state.created_at,
            updated_at=state.updated_at,
        )
