from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.agents.tools.customer_tools import create_ticket, get_ticket
from src.ingestion.seed_data import seed_database
from src.models.db import Ticket, configure_database, session_scope


@pytest.fixture()
def seeded_database(tmp_path: Path) -> None:
    configure_database(f"sqlite:///{(tmp_path / 'side-effect-test.db').as_posix()}")
    seed_database()


def _ticket_count() -> int:
    with session_scope() as session:
        return int(session.scalar(select(func.count()).select_from(Ticket)) or 0)


def test_create_ticket_persists_a_real_sandbox_side_effect(seeded_database: None) -> None:
    before = _ticket_count()

    result = create_ticket(
        "CUS-001",
        "ÄÆ¡n giao cháº­m",
        "Vui lÃ²ng kiá»ƒm tra Ä‘Æ¡n hÃ ng mock ORD-001.",
        request_id="REQ-CREATE-001",
    )

    assert result["ok"] is True
    assert result["status"] == "created"
    assert result["data"]["status"] == "open"
    assert _ticket_count() == before + 1

    persisted = get_ticket(result["data"]["ticket_id"])
    assert persisted["ok"] is True
    assert persisted["data"]["customer_id"] == "CUS-001"
    assert persisted["data"]["subject"] == "ÄÆ¡n giao cháº­m"


def test_create_ticket_does_not_write_for_an_unknown_customer(seeded_database: None) -> None:
    before = _ticket_count()
    result = create_ticket("CUS-404", "Há»— trá»£", "KhÃ´ng Ä‘Æ°á»£c ghi ticket nÃ y.")

    assert result["ok"] is False
    assert result["status"] == "not_found"
    assert _ticket_count() == before


@pytest.mark.parametrize(
    ("subject", "description"),
    [("", "valid"), ("valid", ""), ("x" * 201, "valid"), ("valid", "x" * 4001)],
)
def test_create_ticket_rejects_invalid_content_without_a_side_effect(
    seeded_database: None,
    subject: str,
    description: str,
) -> None:
    before = _ticket_count()
    result = create_ticket("CUS-001", subject, description)
    assert result["ok"] is False
    assert result["status"] == "invalid_input"
    assert _ticket_count() == before


def test_create_ticket_is_idempotent_when_request_id_is_retried(seeded_database: None) -> None:
    before = _ticket_count()
    first = create_ticket("CUS-001", "Retry test", "First call", request_id="REQ-SAME")
    second = create_ticket("CUS-001", "Retry test", "Second call", request_id="REQ-SAME")

    assert first["status"] == "created"
    assert second["status"] == "duplicate"
    assert second["data"]["ticket_id"] == first["data"]["ticket_id"]
    assert _ticket_count() == before + 1
