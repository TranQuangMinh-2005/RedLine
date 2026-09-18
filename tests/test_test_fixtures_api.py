from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api.routers import test_fixtures as fixtures_router
from src.db.models import Ticket, session_scope


def _fixture_settings(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(ENABLE_TEST_FIXTURES=enabled)


def test_ticket_fixture_endpoint_is_disabled_by_default(
    client: TestClient,
    seeded_database: None,
    monkeypatch,
) -> None:
    monkeypatch.setattr(fixtures_router, "get_settings", lambda: _fixture_settings(False))

    response = client.post(
        "/test-fixtures/tickets",
        json={
            "ticket_id": "TKT-ADV-001",
            "customer_id": "CUS-001",
            "subject": "fixture",
            "description": "stored instruction",
        },
    )

    assert response.status_code == 404


def test_ticket_fixture_is_created_and_deleted(
    client: TestClient,
    seeded_database: None,
    monkeypatch,
) -> None:
    monkeypatch.setattr(fixtures_router, "get_settings", lambda: _fixture_settings(True))
    payload = {
        "ticket_id": "TKT-ADV-001",
        "customer_id": "CUS-001",
        "subject": "fixture",
        "description": "stored instruction",
    }

    created = client.post("/test-fixtures/tickets", json=payload)
    assert created.status_code == 201
    with session_scope() as session:
        assert session.get(Ticket, "TKT-ADV-001") is not None

    deleted = client.delete("/test-fixtures/tickets/TKT-ADV-001")
    assert deleted.status_code == 200
    with session_scope() as session:
        assert session.get(Ticket, "TKT-ADV-001") is None
