"""RedLine Ollama gateway — chạy cạnh `ollama serve` trên Kaggle, mở ra ngoài qua ngrok.

Web RedLine (Docker local) kết nối tới gateway như một endpoint OpenAI-compatible
và dùng thêm API quản lý model:

    GET    /health                      không cần token
    GET    /gateway/info                GPU, disk, version Ollama, model đang load
    GET    /gateway/catalog             model nổi bật + đã cài/đang tải
    GET    /gateway/models              model đã cài
    DELETE /gateway/models/{model}      xóa model
    POST   /gateway/pulls {"model"}     bắt đầu tải (chạy nền)
    GET    /gateway/pulls[/{id}]        tiến trình: completed/total/percent/speed
    DELETE /gateway/pulls/{id}          hủy tải
    *      /v1/...                      proxy tới OpenAI API của Ollama (chat, models)

Bảo vệ bằng `Authorization: Bearer $GATEWAY_TOKEN` (cùng giá trị làm API key của
OpenAI client). Chạy:

    GATEWAY_TOKEN=... uvicorn src.gateway.ollama_gateway:app --port 8080
"""

from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field, fields
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask

from src.services.model_catalog import OLLAMA_FEATURED

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "").strip()
MODELS_DIR = os.environ.get("OLLAMA_MODELS") or os.path.expanduser("~/.ollama/models")
MAX_JOBS = 50
MODEL_PATTERN = r"^[A-Za-z0-9._/:-]+$"


def require_token(request: Request) -> None:
    if not GATEWAY_TOKEN:
        return
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), GATEWAY_TOKEN.encode()):
        raise HTTPException(status_code=401, detail="invalid gateway token")


def ollama(method: str, path: str, timeout: float = 15.0, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, f"{OLLAMA_URL}{path}", timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama không phản hồi ({type(exc).__name__})") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=str(detail)[:300])
    return response.json() if response.content else {}


def canonical(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


# ---------------- Pull jobs ----------------

@dataclass
class PullJob:
    model: str
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    state: str = "running"  # running | success | error | cancelled
    status: str = "starting"
    completed: int = 0
    total: int = 0
    percent: float = 0.0
    speed_bps: float = 0.0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict[str, Any]:
        # asdict() deep-copy cả threading.Event -> lỗi; lấy field công khai thủ công.
        return {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")}


class PullManager:
    def __init__(self) -> None:
        self._jobs: dict[str, PullJob] = {}
        self._lock = threading.Lock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)
            return [job.public() for job in jobs]

    def get(self, job_id: str) -> PullJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="pull job not found")
        return job

    def running_for(self, model: str) -> PullJob | None:
        with self._lock:
            return next((j for j in self._jobs.values()
                         if j.state == "running" and canonical(j.model) == canonical(model)), None)

    def start(self, model: str) -> PullJob:
        existing = self.running_for(model)
        if existing:
            return existing
        job = PullJob(model=model)
        with self._lock:
            self._jobs[job.id] = job
            finished = sorted((j for j in self._jobs.values() if j.state != "running"),
                              key=lambda j: j.started_at)
            for old in finished[: max(0, len(self._jobs) - MAX_JOBS)]:
                self._jobs.pop(old.id, None)
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def cancel(self, job_id: str) -> PullJob:
        job = self.get(job_id)
        job._cancel.set()
        return job

    def _run(self, job: PullJob) -> None:
        layers: dict[str, tuple[int, int]] = {}
        sample_time, sample_bytes = time.monotonic(), 0
        try:
            with httpx.stream("POST", f"{OLLAMA_URL}/api/pull",
                              json={"model": job.model, "stream": True},
                              timeout=httpx.Timeout(60.0, read=600.0)) as response:
                if response.status_code >= 400:
                    response.read()
                    raise RuntimeError(response.text[:300] or f"HTTP {response.status_code}")
                for line in response.iter_lines():
                    if job._cancel.is_set():
                        job.state, job.status = "cancelled", "cancelled"
                        return
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise RuntimeError(str(event["error"])[:300])
                    job.status = str(event.get("status", ""))
                    digest = event.get("digest")
                    if digest and event.get("total"):
                        layers[digest] = (int(event.get("completed") or 0), int(event["total"]))
                        job.completed = sum(c for c, _ in layers.values())
                        job.total = sum(t for _, t in layers.values())
                        job.percent = round(job.completed / job.total * 100, 1) if job.total else 0.0
                        now = time.monotonic()
                        if now - sample_time >= 1.0:
                            job.speed_bps = max(0.0, (job.completed - sample_bytes) / (now - sample_time))
                            sample_time, sample_bytes = now, job.completed
                    if job.status == "success":
                        job.state, job.percent, job.speed_bps = "success", 100.0, 0.0
                        return
            raise RuntimeError("pull stream ended without success")
        except Exception as exc:  # noqa: BLE001 — lỗi được trả về qua API tiến trình
            job.state, job.error = "error", str(exc) or type(exc).__name__
        finally:
            job.finished_at = time.time()
            if job.state == "running":
                job.state = "error"


pulls = PullManager()

# ---------------- App ----------------

app = FastAPI(title="RedLine Ollama Gateway", version="0.1.0")
api = APIRouter(dependencies=[Depends(require_token)])


class PullBody(BaseModel):
    model: str = Field(min_length=1, max_length=200, pattern=MODEL_PATTERN)


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        httpx.get(f"{OLLAMA_URL}/api/version", timeout=3).raise_for_status()
        ok = True
    except httpx.HTTPError:
        ok = False
    return {"status": "ok" if ok else "degraded", "ollama": ok}


def _gpus() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10,
    )
    gpus = []
    for line in result.stdout.strip().splitlines() if result.returncode == 0 else []:
        name, total, used = (part.strip() for part in line.split(","))
        gpus.append({"name": name, "memory_total_mb": int(total), "memory_used_mb": int(used)})
    return gpus


def _installed() -> list[dict[str, Any]]:
    rows = ollama("GET", "/api/tags").get("models", [])
    return [
        {
            "id": row.get("name") or row.get("model"),
            "size_gb": round(int(row.get("size") or 0) / 1e9, 2),
            "modified_at": row.get("modified_at"),
            "parameter_size": (row.get("details") or {}).get("parameter_size"),
            "quantization": (row.get("details") or {}).get("quantization_level"),
        }
        for row in rows
    ]


@api.get("/gateway/info")
def info() -> dict[str, Any]:
    os.makedirs(MODELS_DIR, exist_ok=True)
    loaded = ollama("GET", "/api/ps").get("models", [])
    return {
        "gateway": "redline-ollama",
        "version": app.version,
        "ollama_version": ollama("GET", "/api/version").get("version"),
        "gpus": _gpus(),
        "disk_free_gb": round(shutil.disk_usage(MODELS_DIR).free / 1e9, 1),
        "loaded": [{"id": row.get("name"), "size_vram_gb": round(int(row.get("size_vram") or 0) / 1e9, 2)}
                   for row in loaded],
    }


@api.get("/gateway/catalog")
def catalog() -> dict[str, Any]:
    installed = {canonical(row["id"]) for row in _installed()}
    running = {canonical(job["model"]): job for job in pulls.list() if job["state"] == "running"}
    return {
        "models": [
            {**row, "installed": canonical(row["id"]) in installed, "pull": running.get(canonical(row["id"]))}
            for row in OLLAMA_FEATURED
        ]
    }


@api.get("/gateway/models")
def models() -> dict[str, Any]:
    return {"models": _installed()}


@api.delete("/gateway/models/{model:path}")
def delete_model(model: str) -> dict[str, Any]:
    try:
        PullBody(model=model)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="tên model không hợp lệ") from exc
    ollama("DELETE", "/api/delete", json={"model": model})
    return {"deleted": model}


@api.get("/gateway/pulls")
def list_pulls() -> dict[str, Any]:
    return {"jobs": pulls.list()}


@api.post("/gateway/pulls", status_code=202)
def start_pull(body: PullBody) -> dict[str, Any]:
    known = next((row for row in OLLAMA_FEATURED if row["id"] == body.model), None)
    os.makedirs(MODELS_DIR, exist_ok=True)
    free_gb = shutil.disk_usage(MODELS_DIR).free / 1e9
    if known and free_gb < known["size_gb"] * 1.1:
        raise HTTPException(status_code=507, detail=f"không đủ dung lượng: cần ~{known['size_gb']} GB, còn {free_gb:.1f} GB")
    return pulls.start(body.model).public()


@api.get("/gateway/pulls/{job_id}")
def get_pull(job_id: str) -> dict[str, Any]:
    return pulls.get(job_id).public()


@api.delete("/gateway/pulls/{job_id}")
def cancel_pull(job_id: str) -> dict[str, Any]:
    return pulls.cancel(job_id).public()


_proxy_client = httpx.AsyncClient(base_url=OLLAMA_URL, timeout=httpx.Timeout(600.0, connect=10.0))


@api.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def openai_proxy(path: str, request: Request) -> StreamingResponse:
    """Chuyển tiếp OpenAI API (kể cả stream=true) tới Ollama."""
    upstream = _proxy_client.build_request(
        request.method, f"/v1/{path}", params=request.query_params,
        content=await request.body(), headers={"content-type": request.headers.get("content-type", "application/json")},
    )
    try:
        response = await _proxy_client.send(upstream, stream=True)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama không phản hồi ({type(exc).__name__})") from exc
    return StreamingResponse(
        response.aiter_raw(), status_code=response.status_code,
        media_type=response.headers.get("content-type"), background=BackgroundTask(response.aclose),
    )


app.include_router(api)
