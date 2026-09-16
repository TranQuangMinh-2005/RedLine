from __future__ import annotations

import pytest

from src.agents.tools import customer_tools


def test_get_customer_info_returns_one_customer_only(seeded_database: None) -> None:
    result = customer_tools.get_customer_info("CUS-001")

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["data"]["id"] == "CUS-001"
    assert set(result["data"]) == {"id", "name", "email", "phone", "address"}


@pytest.mark.parametrize("customer_id", ["", " ", "X" * 41, None])
def test_get_customer_info_rejects_invalid_input(seeded_database: None, customer_id: object) -> None:
    result = customer_tools.get_customer_info(customer_id)  # type: ignore[arg-type]
    assert result == {
        "ok": False,
        "status": "invalid_input",
        "data": None,
        "error": "customer_id is invalid",
    }


def test_get_customer_info_reports_not_found_without_dumping_database(seeded_database: None) -> None:
    result = customer_tools.get_customer_info("CUS-404")

    assert result["ok"] is False
    assert result["status"] == "not_found"
    assert result["data"] is None
    assert "CUS-001" not in str(result)


def test_get_ticket_returns_one_ticket_only(seeded_database: None) -> None:
    result = customer_tools.get_ticket("TKT-001")

    assert result["ok"] is True
    assert result["data"]["id"] == "TKT-001"
    assert result["data"]["customer_id"] == "CUS-001"
    assert set(result["data"]) == {
        "id",
        "customer_id",
        "subject",
        "description",
        "status",
        "created_at",
        "updated_at",
    }


def test_get_ticket_reports_not_found(seeded_database: None) -> None:
    result = customer_tools.get_ticket("TKT-404")
    assert result["ok"] is False
    assert result["status"] == "not_found"
    assert result["data"] is None


def test_search_knowledge_preserves_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        customer_tools,
        "retrieve",
        lambda query, top_k: [
            {
                "document_id": "shipping-policy",
                "chunk_id": "shipping-policy:0",
                "source_file": "shipping.md",
                "title": "ChÃ­nh sÃ¡ch váº­n chuyá»ƒn",
                "text": "Giao hÃ ng trong 1-2 ngÃ y.",
                "score": 2.0,
                "ignored_internal_field": "must not escape",
            }
        ],
    )

    result = customer_tools.search_knowledge("giao hÃ ng", top_k=1)

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["data"] == [
        {
            "document_id": "shipping-policy",
            "chunk_id": "shipping-policy:0",
            "source_file": "shipping.md",
            "title": "ChÃ­nh sÃ¡ch váº­n chuyá»ƒn",
            "text": "Giao hÃ ng trong 1-2 ngÃ y.",
            "score": 2.0,
        }
    ]


def test_search_knowledge_reports_an_unverified_query_as_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customer_tools, "retrieve", lambda query, top_k: [])
    result = customer_tools.search_knowledge("khÃ´ng cÃ³ trong corpus")
    assert result["ok"] is True
    assert result["status"] == "not_found"
    assert result["data"] == []


@pytest.mark.parametrize(
    ("query", "top_k"),
    [("", 3), ("x" * 1001, 3), ("valid", 0), ("valid", 11), ("valid", "3")],
)
def test_search_knowledge_validates_its_boundary(query: str, top_k: object) -> None:
    result = customer_tools.search_knowledge(query, top_k=top_k)  # type: ignore[arg-type]
    assert result["ok"] is False
    assert result["status"] == "invalid_input"


def test_execute_tool_enforces_the_allowlist() -> None:
    result = customer_tools.execute_tool("drop_database", {})
    assert result["ok"] is False
    assert result["status"] == "invalid_tool"


def test_tool_definitions_and_registry_stay_in_sync() -> None:
    declared = {item["function"]["name"] for item in customer_tools.TOOL_DEFINITIONS}
    assert declared == set(customer_tools.TOOL_FUNCTIONS)
    assert declared == {"get_customer_info", "get_ticket", "search_knowledge", "create_ticket"}


def test_tool_authorization_is_bound_to_the_fixed_scenario_customer(
    seeded_database: None,
) -> None:
    own_customer = customer_tools.execute_tool(
        "get_customer_info",
        {"customer_id": "CUS-001"},
        authorized_customer_id="CUS-001",
    )
    other_customer = customer_tools.execute_tool(
        "get_customer_info",
        {"customer_id": "CUS-002"},
        authorized_customer_id="CUS-001",
    )
    other_ticket = customer_tools.execute_tool(
        "get_ticket",
        {"ticket_id": "TKT-002"},
        authorized_customer_id="CUS-001",
    )

    assert own_customer["ok"] is True
    assert other_customer["status"] == "forbidden"
    assert other_ticket["status"] == "forbidden"
