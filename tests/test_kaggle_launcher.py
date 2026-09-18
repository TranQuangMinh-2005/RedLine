"""Offline coverage for deployment setup, readiness checks and process cleanup."""
import ast
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kaggle_launcher", ROOT / "scripts/kaggle_redline.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_notebook_cells_are_valid_and_have_no_saved_outputs():
    notebook = json.loads((ROOT / "notebooks/kaggle_redline.ipynb").read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]))
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
    sources = "".join("".join(cell["source"]) for cell in notebook["cells"])
    assert "scripts/kaggle_redline.py" in sources
    assert "src.ingestion.seed_data" not in sources
    assert "pip install -e" not in sources


@pytest.mark.parametrize("installed,expected", [
    (["qwen2.5:7b"], False),
    (["qwen2.5:14b-instruct"], False),
    (["qwen2.5:14b"], True),
])
def test_model_cache_requires_exact_tag(installed, expected):
    assert launcher.model_installed("qwen2.5:14b", {
        "models": [{"name": name} for name in installed],
    }) is expected


@pytest.mark.parametrize("events,error", [
    ([{"status": "downloading"}, {"status": "success"}], None),
    ([{"status": "downloading"}, {"error": "model missing"}], "model missing"),
    ([{"status": "downloading"}], "without a success"),
])
def test_pull_requires_success_and_handles_stream_errors(monkeypatch, events, error):
    stream = io.BytesIO(b"\n".join(json.dumps(event).encode() for event in events))
    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *a, **kw: stream)
    if error:
        with pytest.raises(RuntimeError, match=error):
            launcher.pull_model("http://ollama", "qwen2.5:14b")
    else:
        launcher.pull_model("http://ollama", "qwen2.5:14b")


def test_gpu_absence_is_not_reported_as_one_gpu(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    assert launcher.gpu_inventory() == []


def test_smoke_checks_both_modes_and_rejects_blocked_answers(monkeypatch):
    modes = []
    def request(url, payload, **kwargs):
        modes.append(payload["mode"])
        return {"mode": payload["mode"], "reply": "OK", "total_tokens": 4}
    monkeypatch.setattr(launcher, "request_json", request)
    launcher.smoke_test("http://target")
    assert modes == ["llm", "agent"]
    monkeypatch.setattr(launcher, "request_json", lambda *a, **kw: {
        "mode": "llm", "reply": "blocked", "guardrail_blocked": True,
    })
    with pytest.raises(RuntimeError, match="blocked"):
        launcher.smoke_test("http://target")


@pytest.mark.parametrize("ui,reuse,fail", [(False, False, False), (True, True, False),
                                          (False, False, True)])
def test_launcher_readiness_and_cleanup(monkeypatch, tmp_path, ui, reuse, fail):
    from pyngrok import ngrok

    monkeypatch.chdir(ROOT)
    runtime = tmp_path / "runtime"
    args = launcher.parse_args(["--runtime-dir", str(runtime)] + (["--ui"] if ui else []))
    monkeypatch.setenv("NGROK_AUTHTOKEN", "test-ngrok-secret")
    monkeypatch.setenv("CANARY_TOKEN", "CANARY-REDLINE-REPLACE-ME")
    monkeypatch.setattr(launcher, "gpu_inventory", lambda: ["T4, 15360 MiB"])
    monkeypatch.setattr(launcher, "require_free_port", lambda _: None)
    monkeypatch.setattr(launcher, "wait_http", lambda *a, **kw: None)
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(launcher.shutil, "disk_usage", lambda _: SimpleNamespace(free=30 * 1024**3))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(launcher.subprocess, "check_output", lambda *a, **kw: "test-commit\n")
    children = []
    def spawn(command, **kwargs):
        process = SimpleNamespace(pid=10000 + len(children), returncode=None,
                                  command=command, env=kwargs["env"])
        process.poll = lambda: process.returncode
        def wait(**kwargs):
            process.returncode = 0
            return 0
        process.wait = wait
        children.append(process)
        return process
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    killed = []
    monkeypatch.setattr(launcher.os, "killpg", lambda pid, sig: killed.append(pid), raising=False)
    tags_calls = 0
    def request(url, *a, **kw):
        nonlocal tags_calls
        if url.endswith("/api/tags"):
            tags_calls += 1
            if tags_calls == 1 and not reuse:
                raise OSError("no daemon")
            return {"models": [{"name": args.model}]}
        if url.endswith("/api/ps"):
            return {"models": [{"name": args.model, "size_vram": 9_000_000_000}]}
        return {}
    monkeypatch.setattr(launcher, "request_json", request)
    def smoke(_):
        if fail:
            raise RuntimeError("smoke failure")
        (runtime / "target.log").write_text(json.dumps({
            "event": "tool_completed", "tool_name": "search_knowledge", "result_status": "success",
        }) + "\n")
    monkeypatch.setattr(launcher, "smoke_test", smoke)
    tunnels = []
    def connect(*a, **kw):
        tunnels.append(a)
        return SimpleNamespace(public_url="https://example.ngrok.test")
    monkeypatch.setattr(ngrok, "connect", connect)
    disconnected = []
    monkeypatch.setattr(ngrok, "disconnect", lambda *a, **kw: disconnected.append(a))
    monkeypatch.setattr(ngrok, "kill", lambda **kw: None)
    def stop(_):
        info = json.loads((runtime / "status.json").read_text())
        assert info["state"] == "ready"
        assert info["api_url"].endswith("/api") is ui
        assert "CANARY" not in json.dumps(info)
        raise KeyboardInterrupt
    monkeypatch.setattr(launcher.time, "sleep", stop)
    with pytest.raises(RuntimeError if fail else KeyboardInterrupt):
        launcher.run(args)
    services = [child for child in children
                if "serve" in child.command or "uvicorn" in child.command or "start" in child.command]
    assert set(killed) == {child.pid for child in services}
    assert len(children) == (3 + int(not reuse) + 3 * int(ui))
    assert bool(tunnels) is (not fail)
    assert bool(disconnected) is (not fail)
    backend = next(child for child in children if "uvicorn" in child.command)
    assert backend.env["CANARY_TOKEN"] != "CANARY-REDLINE-REPLACE-ME"
    assert backend.env["LLM_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert backend.env["DATABASE_URL"].endswith("runtime/redline.db")
    assert json.loads((runtime / "status.json").read_text())["state"] == ("failed" if fail else "stopped")
