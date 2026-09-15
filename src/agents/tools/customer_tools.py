"""Allowlisted read and sandbox side-effect tools for the target agent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.db import Customer, Ticket, session_scope
from src.services.rag_service import retrieve

MAX_QUERY_LENGTH = 1000
MAX_SUBJECT_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4000


def _result(*, data: Any = None, status: str = "success", error: str | None = None) -> dict[str, Any]:
    return {"ok": error is None, "status": status, "data": data, "error": error}


def _iso(value: datetime) -> str:
    return value.isoformat()


def _with_session(session: Session | None):
    return session_scope() if session is None else _borrowed_session(session)


class _borrowed_session:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, exc_type, exc, traceback) -> bool:  # type: ignore[no-untyped-def]
        return False


def get_customer_info(customer_id: str, *, session: Session | None = None) -> dict[str, Any]:
    customer_id = customer_id.strip() if isinstance(customer_id, str) else ""
    if not customer_id or len(customer_id) > 40:
        return _result(status="invalid_input", error="customer_id is invalid")
    try:
        with _with_session(session) as db:
            customer = db.get(Customer, customer_id)
            if customer is None:
                return _result(status="not_found", error="customer not found")
            return _result(data={
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "phone": customer.phone,
                "address": customer.address,
            })
    except SQLAlchemyError:
        return _result(status="tool_error", error="customer database unavailable")


def get_ticket(ticket_id: str, *, session: Session | None = None) -> dict[str, Any]:
    ticket_id = ticket_id.strip() if isinstance(ticket_id, str) else ""
    if not ticket_id or len(ticket_id) > 40:
        return _result(status="invalid_input", error="ticket_id is invalid")
    try:
        with _with_session(session) as db:
            ticket = db.get(Ticket, ticket_id)
            if ticket is None:
                return _result(status="not_found", error="ticket not found")
            return _result(data={
                "id": ticket.id,
                "customer_id": ticket.customer_id,
                "subject": ticket.subject,
                "description": ticket.description,
                "status": ticket.status,
                "created_at": _iso(ticket.created_at),
                "updated_at": _iso(ticket.updated_at),
            })
    except SQLAlchemyError:
        return _result(status="tool_error", error="ticket database unavailable")


def search_knowledge(query: str, top_k: int = 3) -> dict[str, Any]:
    query = query.strip() if isinstance(query, str) else ""
    if not query or len(query) > MAX_QUERY_LENGTH or not isinstance(top_k, int) or not 1 <= top_k <= 10:
        return _result(status="invalid_input", error="query or top_k is invalid")
    try:
        items = retrieve(query, top_k=top_k)
        data = [{
            "document_id": item["document_id"],
            "chunk_id": item["chunk_id"],
            "source_file": item["source_file"],
            "title": item.get("title", ""),
            "text": item["text"],
            "score": item["score"],
        } for item in items]
        return _result(data=data, status="success" if data else "not_found")
    except (OSError, RuntimeError, ValueError):
        return _result(status="tool_error", error="knowledge index unavailable")


def create_ticket(
    customer_id: str,
    subject: str,
    description: str,
    request_id: str | None = None,
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    customer_id = customer_id.strip() if isinstance(customer_id, str) else ""
    subject = subject.strip() if isinstance(subject, str) else ""
    description = description.strip() if isinstance(description, str) else ""
    request_id = request_id.strip() if isinstance(request_id, str) else None
    if not customer_id or len(customer_id) > 40:
        return _result(status="invalid_input", error="customer_id is invalid")
    if not subject or len(subject) > MAX_SUBJECT_LENGTH:
        return _result(status="invalid_input", error="subject is invalid")
    if not description or len(description) > MAX_DESCRIPTION_LENGTH:
        return _result(status="invalid_input", error="description is invalid")
    if request_id and len(request_id) > 100:
        return _result(status="invalid_input", error="request_id is invalid")
    try:
        with _with_session(session) as db:
            if db.get(Customer, customer_id) is None:
                return _result(status="not_found", error="customer not found")
            if request_id:
                existing = db.scalar(select(Ticket).where(Ticket.request_id == request_id))
                if existing is not None:
                    return _result(data={"ticket_id": existing.id, "status": existing.status, "created_at": _iso(existing.created_at)}, status="duplicate")
            ticket = Ticket(
                id=f"TKT-{uuid4().hex[:12].upper()}",
                customer_id=customer_id,
                subject=subject,
                description=description,
                status="open",
                request_id=request_id,
            )
            db.add(ticket)
            db.flush()
            return _result(data={"ticket_id": ticket.id, "status": ticket.status, "created_at": _iso(ticket.created_at)}, status="created")
    except SQLAlchemyError:
        return _result(status="tool_error", error="ticket could not be created")


TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_customer_info": get_customer_info,
    "get_ticket": get_ticket,
    "search_knowledge": search_knowledge,
    "create_ticket": create_ticket,
}

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "get_customer_info", "description": "Lay thong tin mot khach hang mock theo ID.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_ticket", "description": "Lay mot ticket ho tro mock theo ID.", "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "search_knowledge", "description": "Tim chinh sach trong kho tai lieu sandbox.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "create_ticket", "description": "Tao ticket ho tro moi trong sandbox.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "subject": {"type": "string"}, "description": {"type": "string"}, "request_id": {"type": "string"}}, "required": ["customer_id", "subject", "description"], "additionalProperties": False}}},
]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return _result(status="invalid_tool", error="tool is not allowlisted")
    try:
        return function(**arguments)
    except TypeError:
        return _result(status="invalid_input", error="tool arguments are invalid")
