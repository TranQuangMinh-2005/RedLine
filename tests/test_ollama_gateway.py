"""Kaggle Ollama gateway: auth, pull progress tracking and serialization (offline)."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.gateway import ollama_gateway as gw


class FakeStream:
    status_code = 200
    text = ""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    def iter_lines(self):
        for event in self.events:
            yield json.dumps(event)

    def read(self) -> bytes:
        return b""


def wait_done(job: gw.PullJob) -> None:
    deadline = time.monotonic() + 5
    while job.state == "running" and time.monotonic() < deadline:
        time.sleep(0.01)


def patch_stream(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
    @contextmanager
    def fake_stream(*_args: Any, **_kwargs: Any):
        yield FakeStream(events)

    monkeypatch.setattr(gw.httpx, "stream", fake_stream)


def test_pull_progress_aggregates_layers_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_stream(monkeypatch, [
        {"status": "pulling manifest"},
        {"status": "pulling a", "digest": "sha256:a", "total": 300, "completed": 300},
        {"status": "pulling b", "digest": "sha256:b", "total": 100, "completed": 50},
        {"status": "success"},
    ])
    job = gw.PullManager().start("qwen3.5:4b")
    wait_done(job)
    assert job.state == "success" and job.percent == 100.0
    assert (job.completed, job.total) == (350, 400)
    public = job.public()
    json.dumps(public)
    assert "_cancel" not in public


def test_pull_error_event_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_stream(monkeypatch, [{"status": "pulling manifest"}, {"error": "file does not exist"}])
    job = gw.PullManager().start("missing:1b")
    wait_done(job)
    assert job.state == "error" and "does not exist" in job.error


def test_stream_without_success_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_stream(monkeypatch, [{"status": "pulling manifest"}])
    job = gw.PullManager().start("x:1b")
    wait_done(job)
    assert job.state == "error"


def test_gateway_token_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "s3cret-token-value")
    client = TestClient(gw.app)
    assert client.get("/gateway/pulls").status_code == 401
    assert client.get("/gateway/pulls", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/gateway/pulls", headers={"Authorization": "Bearer s3cret-token-value"})
    assert ok.status_code == 200 and "jobs" in ok.json()


def test_invalid_model_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gw, "GATEWAY_TOKEN", "")
    client = TestClient(gw.app)
    assert client.post("/gateway/pulls", json={"model": "rm -rf /"}).status_code == 422


def test_gateway_notebook_cells_are_valid_and_have_no_outputs() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root / "notebooks/kaggle_ollama_gateway.ipynb").read_text())
    sources = ""
    for cell in notebook["cells"]:
        sources += "".join(cell["source"])
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]))
            assert cell["execution_count"] is None and cell["outputs"] == []
    assert "scripts/kaggle_gateway.py" in sources


def test_gateway_launcher_parses_defaults() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts/kaggle_gateway.py"
    spec = importlib.util.spec_from_file_location("kaggle_gateway", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = module.parse_args([])
    assert args.models == "qwen3.5:4b" and args.port == 8080
