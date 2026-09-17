"""Runtime endpoint/model selection (/config/llm) without network access."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.routers import llm_config
from src.services import llm_runtime, model_gateway
from src.services.model_catalog import DEFAULT_GROQ_MODEL, annotate, GROQ_FEATURED

GROQ_IDS = ["whisper-large-v3", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "groq/compound"]


@pytest.fixture()
def fake_endpoints(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    def list_ids(endpoint: llm_runtime.LLMEndpoint) -> list[str]:
        seen.append(endpoint)
        if endpoint.kind == "groq":
            return GROQ_IDS
        return ["qwen3.5:4b", "llama3.2:3b"]

    monkeypatch.setattr(model_gateway, "list_model_ids", list_ids)
    monkeypatch.setattr(model_gateway, "gateway_info", lambda endpoint: None)
    return seen


def test_groq_preset_defaults_to_gpt_oss_20b() -> None:
    assert llm_runtime.preset("groq").model == DEFAULT_GROQ_MODEL == "openai/gpt-oss-20b"


def test_read_config_never_exposes_api_keys(client: TestClient) -> None:
    llm_runtime.set_custom_connection("https://example.ngrok-free.app", "gateway-secret-token")
    body = client.get("/config/llm").text
    assert "gateway-secret-token" not in body
    custom = next(e for e in client.get("/config/llm").json()["endpoints"] if e["kind"] == "custom")
    assert custom["base_url"] == "https://example.ngrok-free.app/v1"
    assert custom["has_api_key"] is True


def test_discover_groq_filters_non_chat_and_puts_featured_first(
    client: TestClient, fake_endpoints: list[Any]
) -> None:
    response = client.post("/config/llm/discover", json={"endpoint": "groq"})
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["models"]]
    assert ids == ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def test_select_model_switches_runtime_and_config_hash(
    client: TestClient, fake_endpoints: list[Any]
) -> None:
    before = client.get("/health").json()["target_config_hash"]
    response = client.post(
        "/config/llm",
        json={"endpoint": "custom", "base_url": "http://kaggle.example", "api_key": "tok", "model": "qwen3.5:4b"},
    )
    assert response.status_code == 200
    active = llm_runtime.get_active()
    assert (active.kind, active.base_url, active.model, active.api_key) == (
        "custom", "http://kaggle.example/v1", "qwen3.5:4b", "tok")
    health = client.get("/health").json()
    assert health["llm"]["model"] == "qwen3.5:4b"
    assert health["target_config_hash"] != before


def test_select_unknown_model_is_rejected(client: TestClient, fake_endpoints: list[Any]) -> None:
    response = client.post("/config/llm", json={"endpoint": "groq", "model": "not-a-model"})
    assert response.status_code == 422
    assert llm_runtime.get_active().kind == "env"


@pytest.mark.parametrize("url", ["ftp://host/v1", "file:///etc/passwd", "not a url"])
def test_custom_endpoint_requires_http_url(client: TestClient, url: str) -> None:
    response = client.post("/config/llm/discover", json={"endpoint": "custom", "base_url": url})
    assert response.status_code == 422


def test_custom_key_is_kept_when_omitted_for_same_url() -> None:
    llm_runtime.set_custom_connection("https://gw.example/v1", "first")
    assert llm_runtime.set_custom_connection("https://gw.example/", None) == ("https://gw.example/v1", "first")
    assert llm_runtime.set_custom_connection("https://other.example", None)[1] == ""


def test_gateway_routes_require_configured_custom_endpoint(client: TestClient) -> None:
    assert client.get("/config/llm/gateway/catalog").status_code == 409


def test_gateway_errors_are_mapped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    llm_runtime.set_custom_connection("https://gw.example", "bad")

    def deny(*_args: Any, **_kwargs: Any) -> Any:
        raise model_gateway.GatewayError("endpoint từ chối API key/token", 401)

    monkeypatch.setattr(model_gateway, "call", deny)
    assert client.get("/config/llm/gateway/pulls").status_code == 401
    assert client.post("/config/llm/gateway/pulls", json={"model": "bad model!"}).status_code == 422


def test_cannot_delete_active_model(client: TestClient) -> None:
    llm_runtime.set_custom_connection("https://gw.example", "tok")
    llm_runtime.set_active(llm_runtime.preset("custom", "qwen3.5:4b"))
    assert client.delete("/config/llm/gateway/models/qwen3.5:4b").status_code == 409


def test_annotate_matches_latest_tag() -> None:
    rows = annotate(["foo", "openai/gpt-oss-20b"], GROQ_FEATURED)
    assert rows[0]["id"] == "openai/gpt-oss-20b" and rows[0]["featured"]
    assert rows[1] == {"id": "foo", "featured": False}
