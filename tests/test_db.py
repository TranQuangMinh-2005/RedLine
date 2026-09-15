from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.ingestion.seed_data import CUSTOMERS, ORDERS, TICKETS, seed_database
from src.models.db import Customer, Order, Ticket, configure_database, init_db, session_scope


@pytest.fixture()
def isolated_database(tmp_path: Path) -> str:
    database_url = f"sqlite:///{(tmp_path / 'day2-test.db').as_posix()}"
    configure_database(database_url)
    init_db()
    return database_url


def _count(model: type[Customer] | type[Order] | type[Ticket]) -> int:
    with session_scope() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_database_creates_the_deterministic_mock_dataset(isolated_database: str) -> None:
    assert len(CUSTOMERS) >= 10
    assert len(ORDERS) >= 20
    assert len(TICKETS) >= 12
    assert len({row["id"] for row in CUSTOMERS}) == len(CUSTOMERS)
    assert len({row["id"] for row in ORDERS}) == len(ORDERS)
    assert len({row["id"] for row in TICKETS}) == len(TICKETS)
    assert len({row["status"] for row in ORDERS}) >= 7
    assert {"open", "in_progress", "resolved", "closed"}.issubset(
        {row["status"] for row in TICKETS}
    )
    assert all(str(row["email"]).endswith(".test") for row in CUSTOMERS)
    assert all("gia lap" in str(row["address"]).casefold() for row in CUSTOMERS)

    created = seed_database()

    assert created == {
        "customers": len(CUSTOMERS),
        "orders": len(ORDERS),
        "tickets": len(TICKETS),
    }
    assert _count(Customer) == len(CUSTOMERS)
    assert _count(Order) == len(ORDERS)
    assert _count(Ticket) == len(TICKETS)

    with session_scope() as session:
        customer = session.get(Customer, "CUS-001")
        order = session.get(Order, "ORD-001")
        ticket = session.get(Ticket, "TKT-001")
        assert customer is not None and customer.email.endswith(".test")
        assert order is not None and order.customer_id == "CUS-001"
        assert ticket is not None and ticket.customer_id == "CUS-001"


def test_seed_database_is_idempotent(isolated_database: str) -> None:
    first = seed_database()
    second = seed_database()

    assert first == {
        "customers": len(CUSTOMERS),
        "orders": len(ORDERS),
        "tickets": len(TICKETS),
    }
    assert second == {"customers": 0, "orders": 0, "tickets": 0}
    assert _count(Customer) == len(CUSTOMERS)
    assert _count(Order) == len(ORDERS)
    assert _count(Ticket) == len(TICKETS)


def test_foreign_key_rejects_an_order_for_an_unknown_customer(isolated_database: str) -> None:
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(
                Order(
                    id="ORD-INVALID",
                    customer_id="CUS-DOES-NOT-EXIST",
                    product_name="Mock product",
                    status="processing",
                    amount=1,
                    shipping_address="Mock address",
                )
            )

    assert _count(Order) == 0


def test_session_scope_rolls_back_the_whole_failed_transaction(isolated_database: str) -> None:
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(
                Customer(
                    id="CUS-ROLLBACK",
                    name="Rollback Test",
                    email="duplicate@example.test",
                    phone="0900000999",
                    address="Mock address",
                )
            )
            session.add(
                Customer(
                    id="CUS-ROLLBACK-2",
                    name="Rollback Test 2",
                    email="duplicate@example.test",
                    phone="0900000998",
                    address="Mock address",
                )
            )

    assert _count(Customer) == 0
