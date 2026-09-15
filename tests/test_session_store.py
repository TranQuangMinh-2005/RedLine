from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.agents.session import InMemorySessionStore, SessionLimitError


def test_store_creates_a_uuid_session_and_preserves_message_order() -> None:
    store = InMemorySessionStore(max_messages=4)
    session = store.create_session()

    assert session.session_id
    store.append_message(session.session_id, "user", "MÃ£ Ä‘Æ¡n cá»§a tÃ´i lÃ  ORD-001")
    store.append_message(session.session_id, "assistant", "TÃ´i Ä‘Ã£ ghi nháº­n.")

    loaded = store.get_session(session.session_id)
    assert loaded is not None
    assert [message.as_dict() for message in loaded.messages] == [
        {"role": "user", "content": "MÃ£ Ä‘Æ¡n cá»§a tÃ´i lÃ  ORD-001"},
        {"role": "assistant", "content": "TÃ´i Ä‘Ã£ ghi nháº­n."},
    ]
    assert loaded.updated_at >= loaded.created_at


def test_sessions_are_isolated_and_return_defensive_copies() -> None:
    store = InMemorySessionStore()
    store.create_session("session-a")
    store.create_session("session-b")
    store.append_message("session-a", "user", "ORD-001")

    copy_a = store.get_session("session-a")
    assert copy_a is not None
    copy_a.messages.clear()

    loaded_a = store.get_session("session-a")
    loaded_b = store.get_session("session-b")
    assert loaded_a is not None and len(loaded_a.messages) == 1
    assert loaded_b is not None and loaded_b.messages == []


def test_session_limit_is_enforced_without_dropping_existing_history() -> None:
    store = InMemorySessionStore(max_messages=2)
    store.append_message("limited", "user", "one")
    store.append_message("limited", "assistant", "two")

    with pytest.raises(SessionLimitError):
        store.append_message("limited", "user", "three")

    loaded = store.get_session("limited")
    assert loaded is not None and len(loaded.messages) == 2


def test_store_rejects_roles_that_could_inject_a_system_message() -> None:
    store = InMemorySessionStore()
    with pytest.raises(ValueError, match="role"):
        store.append_message("s", "system", "malicious system override")


def test_clear_session_removes_only_the_requested_session() -> None:
    store = InMemorySessionStore()
    store.create_session("one")
    store.create_session("two")

    assert store.clear_session("one") is True
    assert store.clear_session("one") is False
    assert store.get_session("one") is None
    assert store.get_session("two") is not None


def test_concurrent_appends_do_not_lose_messages() -> None:
    store = InMemorySessionStore(max_messages=100)
    store.create_session("shared")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda value: store.append_message("shared", "user", str(value)), range(50)))

    loaded = store.get_session("shared")
    assert loaded is not None
    assert len(loaded.messages) == 50
    assert {message.content for message in loaded.messages} == {str(value) for value in range(50)}
