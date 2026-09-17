"""Prompt Guard 2 server — phân loại prompt injection / jailbreak chạy local trên CPU.

Model: meta-llama/Llama-Prompt-Guard-2-86M (mDeBERTa, đa ngôn ngữ). Nhãn 1 = MALICIOUS.
Văn bản dài được chia cửa sổ 512 token (chồng lấn), điểm = max các cửa sổ, vì
payload injection có thể nằm ở bất kỳ đâu trong đoạn.

    POST /classify {"texts": ["..."]} -> {"results": [{"score": 0.99, "label": "MALICIOUS"}]}
    GET  /health

Model tải lần đầu từ Hugging Face (gated: cần HF_TOKEN đã được Meta duyệt) vào MODEL_DIR.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_ID = os.environ.get("PROMPT_GUARD_MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-86M")
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models/Llama-Prompt-Guard-2-86M"))
MAX_TOKENS = 512
STRIDE = 128
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "4")))

app = FastAPI(title="RedLine Prompt Guard", version="0.1.0")
_state: dict = {"status": "loading", "error": None}
_lock = threading.Lock()


def _load() -> None:
    try:
        # model.safetensors chỉ xuất hiện khi tải xong (đang tải là *.incomplete trong .cache).
        if not (MODEL_DIR / "model.safetensors").exists():
            from huggingface_hub import snapshot_download

            token = os.environ.get("HF_TOKEN") or None
            if not token:
                raise RuntimeError("thiếu HF_TOKEN để tải model gated " + MODEL_ID)
            _state["status"] = "downloading"
            snapshot_download(MODEL_ID, local_dir=MODEL_DIR, token=token,
                              allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"])
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).eval()
        _state.update(tokenizer=tokenizer, model=model, status="ready",
                      labels=model.config.id2label)
    except Exception as exc:  # noqa: BLE001 — lỗi được trả qua /health
        _state.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500])


threading.Thread(target=_load, daemon=True).start()


class ClassifyRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=32)


def _score(text: str) -> float:
    tokenizer, model = _state["tokenizer"], _state["model"]
    encoded = tokenizer(
        text, truncation=True, max_length=MAX_TOKENS, stride=STRIDE,
        return_overflowing_tokens=True, padding=True, return_tensors="pt",
    )
    encoded.pop("overflow_to_sample_mapping", None)
    with torch.inference_mode():
        logits = model(**encoded).logits
    return float(torch.softmax(logits, dim=-1)[:, 1].max())


@app.get("/health")
def health() -> dict:
    return {"status": _state["status"], "model": MODEL_ID, "error": _state["error"]}


@app.post("/classify")
def classify(req: ClassifyRequest) -> dict:
    if _state["status"] != "ready":
        raise HTTPException(status_code=503, detail=f"model {_state['status']}: {_state['error'] or ''}")
    started = time.monotonic()
    with _lock:  # model CPU dùng chung, tránh tranh thread
        scores = [_score(text) if text.strip() else 0.0 for text in req.texts]
    return {
        "model": MODEL_ID,
        "latency_s": round(time.monotonic() - started, 3),
        "results": [{"score": round(s, 6), "label": "MALICIOUS" if s >= 0.5 else "BENIGN"} for s in scores],
    }
