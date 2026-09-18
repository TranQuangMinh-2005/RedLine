from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import logging_config
from src.agents.session import InMemorySessionStore
from src.api.routers import chat as chat_router
from src.db.models import configure_database, init_db
from src.db.seed_data import seed_database
from src.guardrails import llama_guard, prompt_guard
from src.guardrails import state as defense_state
from src.main import app
from src.services import llm_runtime
from src.services import redact as redact_module
from src.services.rate_limit import roe_budget


@pytest.fixture(autouse=True)
def reset_runtime_defense_profile() -> Iterator[None]:
    defense_state.reset_to_default()
    llm_runtime.reset_to_default()
    llama_guard.reset_to_default()
    prompt_guard.reset_to_default()
    roe_budget.reset()
    yield
    defense_state.reset_to_default()
    llm_runtime.reset_to_default()
    llama_guard.reset_to_default()
    prompt_guard.reset_to_default()
    roe_budget.reset()


@pytest.fixture()
def isolated_database(tmp_path: Path) -> str:
    database_url = f"sqlite:///{(tmp_path / 'isolated-test.db').as_posix()}"
    configure_database(database_url)
    init_db()
    return database_url


@pytest.fixture()
def seeded_database(tmp_path: Path) -> None:
    configure_database(f"sqlite:///{(tmp_path / 'seeded-test.db').as_posix()}")
    seed_database()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(chat_router, "session_store", InMemorySessionStore(max_messages=50))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sensitive_settings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        LLM_API_KEY="gsk-super-secret-test-key",
        LLM_SECONDARY_API_KEY="gsk-secondary-secret-test-key",
        CANARY_TOKEN="CANARY-PRIVATE-TEST",
        LOG_LEVEL="INFO",
        DEFENSE_PROFILE="none",
        target_config_hash="config123",
    )
    monkeypatch.setattr(redact_module, "get_settings", lambda: settings)
    monkeypatch.setattr(logging_config, "get_settings", lambda: settings)
    return settings
