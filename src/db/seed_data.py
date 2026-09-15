"""Idempotently seed deterministic mock records into the sandbox database."""

from __future__ import annotations

from decimal import Decimal

from src.db.models import Customer, Order, Ticket, init_db, session_scope

CUSTOMERS = (
    {"id": "CUS-001", "name": "Khach Hang Mau 01", "email": "customer01@example.test", "phone": "0900000001", "address": "Dia chi gia lap 01, Viet Nam"},
    {"id": "CUS-002", "name": "Khach Hang Mau 02", "email": "customer02@example.test", "phone": "0900000002", "address": "Dia chi gia lap 02, Viet Nam"},
    {"id": "CUS-003", "name": "Khach Hang Mau 03", "email": "customer03@example.test", "phone": "0900000003", "address": "Dia chi gia lap 03, Viet Nam"},
    {"id": "CUS-004", "name": "Khach Hang Mau 04", "email": "customer04@example.test", "phone": "0900000004", "address": "Dia chi gia lap 04, Viet Nam"},
    {"id": "CUS-005", "name": "Khach Hang Mau 05", "email": "customer05@example.test", "phone": "0900000005", "address": "Dia chi gia lap 05, Viet Nam"},
    {"id": "CUS-006", "name": "Khach Hang Mau 06", "email": "customer06@example.test", "phone": "0900000006", "address": "Dia chi gia lap 06, Viet Nam"},
    {"id": "CUS-007", "name": "Khach Hang Mau 07", "email": "customer07@example.test", "phone": "0900000007", "address": "Dia chi gia lap 07, Viet Nam"},
    {"id": "CUS-008", "name": "Khach Hang Mau 08", "email": "customer08@example.test", "phone": "0900000008", "address": "Dia chi gia lap 08, Viet Nam"},
    {"id": "CUS-009", "name": "Khach Hang Mau 09", "email": "customer09@example.test", "phone": "0900000009", "address": "Dia chi gia lap 09, Viet Nam"},
    {"id": "CUS-010", "name": "Khach Hang Mau 10", "email": "customer10@example.test", "phone": "0900000010", "address": "Dia chi gia lap 10, Viet Nam"},
)
ORDERS = (
    {"id": "ORD-001", "customer_id": "CUS-001", "product_name": "Tai nghe mau", "status": "shipping", "amount": Decimal("490000.00"), "shipping_address": "Dia chi gia lap 01, Viet Nam"},
    {"id": "ORD-002", "customer_id": "CUS-002", "product_name": "Ban phim mau", "status": "delivered", "amount": Decimal("850000.00"), "shipping_address": "Dia chi gia lap 02, Viet Nam"},
    {"id": "ORD-003", "customer_id": "CUS-003", "product_name": "Chuot mau", "status": "processing", "amount": Decimal("320000.00"), "shipping_address": "Dia chi gia lap 03, Viet Nam"},
    {"id": "ORD-004", "customer_id": "CUS-004", "product_name": "Webcam mau", "status": "pending_payment", "amount": Decimal("610000.00"), "shipping_address": "Dia chi gia lap 04, Viet Nam"},
    {"id": "ORD-005", "customer_id": "CUS-005", "product_name": "Loa mau", "status": "confirmed", "amount": Decimal("730000.00"), "shipping_address": "Dia chi gia lap 05, Viet Nam"},
    {"id": "ORD-006", "customer_id": "CUS-006", "product_name": "Cap mau", "status": "cancelled", "amount": Decimal("120000.00"), "shipping_address": "Dia chi gia lap 06, Viet Nam"},
    {"id": "ORD-007", "customer_id": "CUS-007", "product_name": "Sac mau", "status": "return_requested", "amount": Decimal("280000.00"), "shipping_address": "Dia chi gia lap 07, Viet Nam"},
    {"id": "ORD-008", "customer_id": "CUS-008", "product_name": "De laptop mau", "status": "shipping", "amount": Decimal("410000.00"), "shipping_address": "Dia chi gia lap 08, Viet Nam"},
    {"id": "ORD-009", "customer_id": "CUS-009", "product_name": "Hub USB mau", "status": "delivered", "amount": Decimal("350000.00"), "shipping_address": "Dia chi gia lap 09, Viet Nam"},
    {"id": "ORD-010", "customer_id": "CUS-010", "product_name": "Micro mau", "status": "processing", "amount": Decimal("920000.00"), "shipping_address": "Dia chi gia lap 10, Viet Nam"},
    {"id": "ORD-011", "customer_id": "CUS-001", "product_name": "Tai nghe mau B", "status": "confirmed", "amount": Decimal("510000.00"), "shipping_address": "Dia chi gia lap 01, Viet Nam"},
    {"id": "ORD-012", "customer_id": "CUS-002", "product_name": "Ban phim mau B", "status": "shipping", "amount": Decimal("890000.00"), "shipping_address": "Dia chi gia lap 02, Viet Nam"},
    {"id": "ORD-013", "customer_id": "CUS-003", "product_name": "Chuot mau B", "status": "delivered", "amount": Decimal("340000.00"), "shipping_address": "Dia chi gia lap 03, Viet Nam"},
    {"id": "ORD-014", "customer_id": "CUS-004", "product_name": "Webcam mau B", "status": "cancelled", "amount": Decimal("640000.00"), "shipping_address": "Dia chi gia lap 04, Viet Nam"},
    {"id": "ORD-015", "customer_id": "CUS-005", "product_name": "Loa mau B", "status": "pending_payment", "amount": Decimal("760000.00"), "shipping_address": "Dia chi gia lap 05, Viet Nam"},
    {"id": "ORD-016", "customer_id": "CUS-006", "product_name": "Cap mau B", "status": "processing", "amount": Decimal("140000.00"), "shipping_address": "Dia chi gia lap 06, Viet Nam"},
    {"id": "ORD-017", "customer_id": "CUS-007", "product_name": "Sac mau B", "status": "return_requested", "amount": Decimal("300000.00"), "shipping_address": "Dia chi gia lap 07, Viet Nam"},
    {"id": "ORD-018", "customer_id": "CUS-008", "product_name": "De laptop mau B", "status": "confirmed", "amount": Decimal("430000.00"), "shipping_address": "Dia chi gia lap 08, Viet Nam"},
    {"id": "ORD-019", "customer_id": "CUS-009", "product_name": "Hub USB mau B", "status": "shipping", "amount": Decimal("370000.00"), "shipping_address": "Dia chi gia lap 09, Viet Nam"},
    {"id": "ORD-020", "customer_id": "CUS-010", "product_name": "Micro mau B", "status": "delivered", "amount": Decimal("950000.00"), "shipping_address": "Dia chi gia lap 10, Viet Nam"},
)
TICKETS = (
    {"id": "TKT-001", "customer_id": "CUS-001", "subject": "Kiem tra giao hang", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "open"},
    {"id": "TKT-002", "customer_id": "CUS-002", "subject": "Huong dan bao hanh", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "resolved"},
    {"id": "TKT-003", "customer_id": "CUS-003", "subject": "Thanh toan dang kiem tra", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "in_progress"},
    {"id": "TKT-004", "customer_id": "CUS-004", "subject": "Yeu cau da dong", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "closed"},
    {"id": "TKT-005", "customer_id": "CUS-005", "subject": "Kiem tra voucher", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "open"},
    {"id": "TKT-006", "customer_id": "CUS-006", "subject": "Theo doi don", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "in_progress"},
    {"id": "TKT-007", "customer_id": "CUS-007", "subject": "Doi tra hoan tat", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "resolved"},
    {"id": "TKT-008", "customer_id": "CUS-008", "subject": "Yeu cau cu", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "closed"},
    {"id": "TKT-009", "customer_id": "CUS-009", "subject": "Bao mat tai khoan", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "open"},
    {"id": "TKT-010", "customer_id": "CUS-010", "subject": "Kiem tra hoan tien", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "in_progress"},
    {"id": "TKT-011", "customer_id": "CUS-001", "subject": "Da giao thanh cong", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "resolved"},
    {"id": "TKT-012", "customer_id": "CUS-002", "subject": "Ket thuc ho tro", "description": "Du lieu ticket gia lap cho thu nghiem.", "status": "closed"},
)


def seed_database() -> dict[str, int]:
    init_db()
    created = {"customers": 0, "orders": 0, "tickets": 0}
    with session_scope() as session:
        for model, rows, key in ((Customer, CUSTOMERS, "customers"), (Order, ORDERS, "orders"), (Ticket, TICKETS, "tickets")):
            for row in rows:
                if session.get(model, row["id"]) is None:
                    session.add(model(**row))
                    created[key] += 1
    return created


def main() -> None:
    result = seed_database()
    print("Seed complete: " + ", ".join(f"{key}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
