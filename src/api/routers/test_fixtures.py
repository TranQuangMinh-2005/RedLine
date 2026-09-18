"""Ephemeral benchmark fixtures, disabled unless explicitly enabled."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config import get_settings
from src.db.models import Customer, Ticket, session_scope
from src.logging_config import audit_event

router = APIRouter(prefix="/test-fixtures", tags=["test-fixtures"])


class TicketFixtureRequest(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=40)
    customer_id: str = Field(min_length=1, max_length=40)
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)


def _require_enabled() -> None:
    if not get_settings().ENABLE_TEST_FIXTURES:
        raise HTTPException(status_code=404, detail="test fixtures are disabled")


@router.post("/tickets", status_code=201)
def create_ticket_fixture(req: TicketFixtureRequest) -> dict:
    _require_enabled()
    with session_scope() as db:
        if db.get(Customer, req.customer_id) is None:
            raise HTTPException(status_code=422, detail="fixture customer does not exist")
        existing = db.get(Ticket, req.ticket_id)
        if existing is not None:
            db.delete(existing)
            db.flush()
        db.add(
            Ticket(
                id=req.ticket_id,
                customer_id=req.customer_id,
                subject=req.subject,
                description=req.description,
                status="open",
                request_id=None,
            )
        )
    audit_event(
        "ticket_fixture_created",
        request_id=str(uuid4()),
        ticket_id=req.ticket_id,
        customer_id=req.customer_id,
    )
    return {"status": "created", "ticket_id": req.ticket_id}


@router.delete("/tickets/{ticket_id}")
def delete_ticket_fixture(ticket_id: str) -> dict:
    _require_enabled()
    with session_scope() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket fixture not found")
        db.delete(ticket)
    audit_event("ticket_fixture_deleted", request_id=str(uuid4()), ticket_id=ticket_id)
    return {"status": "deleted", "ticket_id": ticket_id}
