"""Run RedLine on Kaggle with local Ollama, optional Next.js UI, and ngrok.

Dependencies are installed by notebooks/kaggle_redline.ipynb using uv.lock.
Run from any directory with the project's Python. Importing this file has no side effects.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def request_json(url, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(f"Service returned an error at {url}: {result['error']}")
    return result


def model_installed(model, tags):
    canonical = model if ":" in model else f"{model}:latest"
    return any(row.get("name") in {model, canonical} or row.get("model") in {model, canonical}
               for row in tags.get("models", []))


def pull_model(base_url, model):
    request = urllib.request.Request(
        f"{base_url}/api/pull",
        data=json.dumps({"model": model, "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    succeeded = False
    last_progress = None
    with urllib.request.urlopen(request, timeout=1800) as response:
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError(f"Ollama pull failed: {event['error']}")
            succeeded = event.get("status") == "success"
            total = event.get("total", 0)
            progress = (f"{int(event.get('completed', 0) / total * 10) * 10}%"
                        if total else event.get("status", ""))
            if progress != last_progress:
                print(f"Model download: {progress}", flush=True)
                last_progress = progress
    if not succeeded:
        raise RuntimeError("Ollama pull ended without a success event")


def gpu_inventory():
    if not shutil.which("nvidia-smi"):
        return []
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    return result.stdout.strip().splitlines() if result.returncode == 0 else []


def require_free_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} is occupied. Stop the previous run first.") from exc


def wait_http(url, process, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Process exited with code {process.returncode}; see runtime logs")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise TimeoutError(f"Service not ready after {timeout}s: {url}")


def smoke_test(base_url):
    """Exercise both modes and a real read-only tool using the configured provider."""
    for mode, message in (
        ("llm", "Chỉ trả lời một từ: OK"),
        ("agent", "Hãy dùng search_knowledge để tìm chính sách vận chuyển và tóm tắt ngắn gọn."),
    ):
        result = request_json(f"{base_url}/chat", {"mode": mode, "message": message}, timeout=600)
        if result.get("mode") != mode or not result.get("reply", "").strip():
            raise RuntimeError(f"Smoke test failed for mode {mode}")
        if result.get("guardrail_blocked"):
            raise RuntimeError(f"Smoke test unexpectedly blocked for mode {mode}")
        print(f"Smoke test {mode}: OK ({result.get('total_tokens', 0)} tokens)", flush=True)


def run(args):
    os.chdir(ROOT)
    runtime = args.runtime_dir.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    status_file = runtime / "status.json"
    lock_file = runtime / "launcher.lock"
    # Hold a process lock for the whole run; stale files do not block subsequent runs.
    import fcntl
    lock = lock_file.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError("A launcher is already running. Stop it before starting again.") from exc
    children = []
    services = []
    handles = []
    tunnel = None
    ngrok = None
    tunnel_config = None

    def spawn(command, log_name, env, cwd=ROOT, service=True):
        handle = (runtime / log_name).open("w")
        handles.append(handle)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        children.append(process)
        if service:
            services.append(process)
        return process

    def checked_run(command, log_name, env, cwd=ROOT):
        print(f"Running setup step: {log_name}", flush=True)
        process = spawn(command, log_name, env, cwd, service=False)
        if process.wait() != 0:
            raise RuntimeError(f"Setup failed; see {runtime / log_name}")
        children.remove(process)

    def write_status(data):
        temporary = runtime / "status.tmp"
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(status_file)

    try:
        write_status({"state": "starting"})
        require_free_port(args.port)
        if args.ui:
            require_free_port(args.ui_port)
        token = os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_AUTH_TOKEN")
        if not token:
            raise RuntimeError("Attach NGROK_AUTH_TOKEN in Kaggle Secrets")
        gpus = gpu_inventory()
        if not gpus:
            raise RuntimeError("No NVIDIA GPU detected. Enable a Kaggle GPU accelerator first.")
        print("Detected GPUs: " + "; ".join(gpus), flush=True)
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(ROOT),
            "LLM_PROVIDER": "ollama",
            "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "LLM_MODEL": args.model,
            "LLM_API_KEY": "ollama",
            "DATABASE_URL": f"sqlite:///{runtime / 'redline.db'}",
            "DEFENSE_PROFILE": args.defense_profile,
            "SCENARIO_CUSTOMER_ID": args.customer_id,
            "ROE_KILL_SWITCH": "false",
            "LLM_TIMEOUT_SECONDS": "300",
        })
        canary = env.get("CANARY_TOKEN", "").strip()
        if not canary or canary == "CANARY-REDLINE-REPLACE-ME":
            env["CANARY_TOKEN"] = "CANARY-" + secrets.token_hex(24)
        # Secrets are passed only to the backend. Never print them or store them in status.
        ollama_url = "http://127.0.0.1:11434"
        try:
            tags = request_json(f"{ollama_url}/api/tags", timeout=3)
            print("Reusing local Ollama server", flush=True)
        except (OSError, ValueError):
            if not shutil.which("ollama"):
                raise RuntimeError("Ollama is not installed. Run the notebook installation cell.")
            models_dir = runtime / "models"
            models_dir.mkdir(exist_ok=True)
            if shutil.disk_usage(models_dir).free < args.min_free_gib * 1024**3:
                raise RuntimeError(f"Need at least {args.min_free_gib} GiB free for Ollama models")
            ollama_env = os.environ.copy()
            ollama_env.update({"OLLAMA_HOST": "127.0.0.1:11434",
                               "OLLAMA_MODELS": str(models_dir),
                               "OLLAMA_KEEP_ALIVE": "30m",
                               "OLLAMA_CONTEXT_LENGTH": str(args.context_length),
                               "OLLAMA_NUM_PARALLEL": "1"})
            ollama = spawn(["ollama", "serve"], "ollama.log", ollama_env)
            wait_http(f"{ollama_url}/api/tags", ollama)
            tags = request_json(f"{ollama_url}/api/tags")
        if not model_installed(args.model, tags):
            pull_model(ollama_url, args.model)
        if not model_installed(args.model, request_json(f"{ollama_url}/api/tags")):
            raise RuntimeError("Requested model tag is still missing after pull")
        # An empty prompt preloads the model without generating a long response.
        request_json(f"{ollama_url}/api/generate", {
            "model": args.model, "prompt": "", "stream": False, "keep_alive": "30m",
            "options": {"num_ctx": args.context_length},
        }, timeout=600)
        loaded = request_json(f"{ollama_url}/api/ps").get("models", [])
        if not any(row.get("size_vram", 0) > 0 for row in loaded
                   if model_installed(args.model, {"models": [row]})):
            raise RuntimeError("Requested model is not loaded on GPU; inspect ollama.log")
        print("Model loaded on GPU (Ollama decides GPU placement).", flush=True)

        checked_run([sys.executable, "-m", "src.db.seed_data"], "seed.log", env)
        checked_run([sys.executable, "scripts/ingest_rag.py"], "ingest.log", env)
        print((runtime / "ingest.log").read_text().strip(), flush=True)
        target = spawn([sys.executable, "-m", "uvicorn", "src.main:app", "--host",
                        "127.0.0.1", "--port", str(args.port)], "target.log", env)
        api = f"http://127.0.0.1:{args.port}"
        wait_http(f"{api}/health", target)
        smoke_test(api)
        # Confirm the agent actually executed retrieval, rather than merely claiming it did.
        events = []
        for line in (runtime / "target.log").read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        if not any(e.get("event") == "tool_completed" and e.get("tool_name") == "search_knowledge"
                   and e.get("result_status") == "success" for e in events):
            raise RuntimeError("Agent smoke test did not execute search_knowledge successfully")

        public_port = args.port
        if args.ui:
            if not shutil.which("node") or not shutil.which("npm"):
                raise RuntimeError("Node.js/npm missing. Install Node >=18.17 or disable UI.")
            ui_env = os.environ.copy()
            ui_env.update({"BACKEND_URL": api, "NEXT_TELEMETRY_DISABLED": "1"})
            # The frontend does not need backend secrets.
            for key in ("CANARY_TOKEN", "LLM_API_KEY", "NGROK_AUTH_TOKEN", "NGROK_AUTHTOKEN"):
                ui_env.pop(key, None)
            checked_run(["npm", "ci", "--no-audit", "--no-fund"],
                        "npm-install.log", ui_env, ROOT / "frontend")
            checked_run(["npm", "run", "build"], "npm-build.log", ui_env, ROOT / "frontend")
            ui = spawn(["npm", "run", "start", "--", "--hostname", "127.0.0.1",
                        "--port", str(args.ui_port)], "frontend.log", ui_env, ROOT / "frontend")
            wait_http(f"http://127.0.0.1:{args.ui_port}/api/health", ui)
            public_port = args.ui_port

        from pyngrok import ngrok as ngrok_module
        from pyngrok.conf import PyngrokConfig
        ngrok = ngrok_module
        tunnel_config = PyngrokConfig(auth_token=token)
        tunnel = ngrok.connect(public_port, "http", pyngrok_config=tunnel_config)
        public = tunnel.public_url
        info = {"state": "ready", "model": args.model, "defense_profile": args.defense_profile,
                "ui_url": public if args.ui else None,
                "api_url": public + "/api" if args.ui else public,
                "local_api_url": api,
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}
        write_status(info)
        print(json.dumps(info, indent=2), flush=True)
        print("Ready. Stop with the notebook Stop cell or Ctrl+C.", flush=True)
        while True:
            if any(child.poll() is not None for child in services):
                raise RuntimeError("A managed service exited; inspect runtime logs")
            time.sleep(2)
    except BaseException as exc:
        write_status({"state": "stopped" if isinstance(exc, KeyboardInterrupt) else "failed",
                      "error_type": type(exc).__name__})
        raise
    finally:
        if ngrok is not None and tunnel_config is not None:
            try:
                if tunnel is not None:
                    ngrok.disconnect(tunnel.public_url, pyngrok_config=tunnel_config)
                ngrok.kill(pyngrok_config=tunnel_config)
            except Exception:
                pass
        for child in reversed(children):
            try:
                # Kill the group even if its leader exited but left descendants running.
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        for handle in handles:
            handle.close()
        lock.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:14b")
    parser.add_argument("--defense-profile", choices=["none", "basic", "strict"], default="none")
    parser.add_argument("--customer-id", default="CUS-001")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=3000)
    parser.add_argument("--ui", action="store_true", help="Serve Next.js and API through one tunnel")
    parser.add_argument("--context-length", type=int, default=8192)
    parser.add_argument("--min-free-gib", type=float, default=15)
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "runs/kaggle")
    return parser.parse_args(argv)


def main():
    def stop(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        run(parse_args())
    except KeyboardInterrupt:
        print("Stopped; managed services cleaned up.", flush=True)
    except Exception as exc:
        # Provider errors can contain request content. Keep notebook output minimal.
        print(f"Startup failed ({type(exc).__name__}): {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
