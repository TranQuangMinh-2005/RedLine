"""Host Ollama models on Kaggle behind the RedLine gateway and an ngrok tunnel.

Web RedLine (Docker on your machine) connects with endpoint "custom":
    base_url = <public_url>/v1, api key = GATEWAY_TOKEN
and can then list, download (with progress) and delete models from the UI.

Dependencies are installed by notebooks/kaggle_ollama_gateway.ipynb using uv.lock.
Importing this file has no side effects.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaggle_redline as base  # noqa: E402  (reuse Ollama/process helpers)

ROOT = base.ROOT
OLLAMA_URL = "http://127.0.0.1:11434"


def run(args):
    os.chdir(ROOT)
    runtime = args.runtime_dir.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    status_file = runtime / "gateway-status.json"
    lock = (runtime / "gateway.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError("A gateway launcher is already running. Stop it first.") from exc
    children, handles = [], []
    ngrok = tunnel = tunnel_config = None

    def spawn(command, log_name, env):
        handle = (runtime / log_name).open("w")
        handles.append(handle)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        children.append(process)
        return process

    def write_status(data):
        temporary = runtime / "gateway-status.tmp"
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(status_file)

    try:
        write_status({"state": "starting"})
        base.require_free_port(args.port)
        ngrok_token = os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_AUTH_TOKEN")
        if not ngrok_token:
            raise RuntimeError("Attach NGROK_AUTH_TOKEN in Kaggle Secrets")
        gateway_token = os.environ.get("GATEWAY_TOKEN", "").strip()
        if len(gateway_token) < 16:
            raise RuntimeError("GATEWAY_TOKEN must be set (>= 16 chars); the tunnel is public")
        gpus = base.gpu_inventory()
        if not gpus and not args.allow_cpu:
            raise RuntimeError("No NVIDIA GPU detected. Enable a Kaggle GPU accelerator first.")
        print("Detected GPUs: " + ("; ".join(gpus) or "none (CPU)"), flush=True)

        models_dir = runtime / "models"
        models_dir.mkdir(exist_ok=True)
        try:
            base.request_json(f"{OLLAMA_URL}/api/tags", timeout=3)
            print("Reusing local Ollama server", flush=True)
        except (OSError, ValueError):
            if not shutil.which("ollama"):
                raise RuntimeError("Ollama is not installed. Run the notebook installation cell.")
            ollama_env = os.environ.copy()
            ollama_env.update({"OLLAMA_HOST": "127.0.0.1:11434",
                               "OLLAMA_MODELS": str(models_dir),
                               "OLLAMA_KEEP_ALIVE": "30m",
                               "OLLAMA_CONTEXT_LENGTH": str(args.context_length),
                               "OLLAMA_MAX_LOADED_MODELS": "1",
                               "OLLAMA_NUM_PARALLEL": "1"})
            ollama = spawn(["ollama", "serve"], "ollama.log", ollama_env)
            base.wait_http(f"{OLLAMA_URL}/api/tags", ollama)

        for model in filter(None, (m.strip() for m in args.models.split(","))):
            if not base.model_installed(model, base.request_json(f"{OLLAMA_URL}/api/tags")):
                print(f"Pre-pulling {model}", flush=True)
                base.pull_model(OLLAMA_URL, model)

        gateway_env = os.environ.copy()
        gateway_env.update({"PYTHONPATH": str(ROOT), "OLLAMA_URL": OLLAMA_URL,
                            "OLLAMA_MODELS": str(models_dir), "GATEWAY_TOKEN": gateway_token,
                            "GATEWAY_CORS_ORIGINS": args.cors_origins})
        for key in ("NGROK_AUTH_TOKEN", "NGROK_AUTHTOKEN"):
            gateway_env.pop(key, None)
        gateway = spawn([sys.executable, "-m", "uvicorn", "src.gateway.ollama_gateway:app",
                         "--host", "127.0.0.1", "--port", str(args.port)], "gateway.log", gateway_env)
        base.wait_http(f"http://127.0.0.1:{args.port}/health", gateway)

        from pyngrok import ngrok as ngrok_module
        from pyngrok.conf import PyngrokConfig
        ngrok = ngrok_module
        tunnel_config = PyngrokConfig(auth_token=ngrok_token)
        tunnel = ngrok.connect(args.port, "http", pyngrok_config=tunnel_config)
        public = tunnel.public_url.replace("http://", "https://", 1)
        # Token is never written to the status file.
        info = {"state": "ready", "public_url": public, "openai_base_url": public + "/v1",
                "local_url": f"http://127.0.0.1:{args.port}"}
        write_status(info)
        print(json.dumps(info, indent=2), flush=True)
        print("Ready. Stop with the notebook Stop cell or Ctrl+C.", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
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
    parser.add_argument("--models", default="qwen3.5:4b",
                        help="comma-separated models to pull before start; empty = none")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--context-length", type=int, default=8192)
    parser.add_argument("--cors-origins", default="*",
                        help='CORS origins for browser tools: "*", comma list, or "" to disable')
    parser.add_argument("--allow-cpu", action="store_true")
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
        print(f"Startup failed ({type(exc).__name__}): {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
