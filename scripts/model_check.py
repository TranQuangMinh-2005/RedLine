"""Kiểm tra model Groq khả dụng và đề xuất model nhẹ cho RedLine.

Agent mode cần tool calling, nên ngoài việc list model, script có thể gọi thử
một request nhỏ kèm tool để xác nhận model thực sự trả về tool_calls.

    python scripts/model_check.py            # chỉ list + đề xuất
    python scripts/model_check.py --probe    # gọi thử tool calling (tốn vài trăm token/model)
    python scripts/model_check.py --ollama   # kiểm tra tag Ollama trong danh mục có trên registry
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.model_catalog import (  # noqa: E402
    GROQ_FEATURED,
    OLLAMA_FEATURED,
    annotate,
    is_groq_chat_model,
)

GROQ_URL = "https://api.groq.com/openai/v1"
PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": "Lấy trạng thái đơn hàng theo mã",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
}


def list_groq(api_key: str) -> list[dict]:
    response = requests.get(f"{GROQ_URL}/models",
                            headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    response.raise_for_status()
    return response.json()["data"]


def probe_tools(api_key: str, model: str) -> str:
    started = time.monotonic()
    response = requests.post(
        f"{GROQ_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Kiểm tra trạng thái đơn ORD-1001."}],
            "tools": [PROBE_TOOL],
            "tool_choice": "auto",
            "max_tokens": 256,
            "temperature": 0,
        },
        timeout=60,
    )
    latency = time.monotonic() - started
    if response.status_code != 200:
        return f"HTTP {response.status_code}"
    message = response.json()["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    if calls and calls[0]["function"]["name"] == "get_order_status":
        return f"tool OK ({latency:.1f}s)"
    return f"no tool call ({latency:.1f}s)"


def check_ollama_registry() -> None:
    print("\nOllama registry (danh mục Kaggle):")
    for row in OLLAMA_FEATURED:
        name, tag = row["id"].split(":")
        response = requests.get(
            f"https://registry.ollama.ai/v2/library/{name}/manifests/{tag}",
            headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
            timeout=30,
        )
        if response.status_code != 200:
            print(f"  {row['id']:<16} MISSING (HTTP {response.status_code})")
            continue
        size = sum(layer["size"] for layer in response.json().get("layers", [])) / 1e9
        print(f"  {row['id']:<16} {size:6.2f} GB  {'light' if row['light'] else ''}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="gọi thử tool calling")
    parser.add_argument("--ollama", action="store_true", help="kiểm tra tag Ollama")
    parser.add_argument("--json", action="store_true", help="in JSON thay vì bảng")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        print("Thiếu LLM_API_KEY trong .env", file=sys.stderr)
        return 1

    models = list_groq(api_key)
    active = [m["id"] for m in models if m.get("active", True)]
    chat_ids = [m for m in active if is_groq_chat_model(m)]
    rows = annotate(chat_ids, GROQ_FEATURED)
    context = {m["id"]: m.get("context_window") for m in models}
    missing = [m["id"] for m in GROQ_FEATURED if m["id"] not in active]

    for row in rows:
        row["context_window"] = context.get(row["id"])
        if args.probe:
            row["probe"] = probe_tools(api_key, row["id"])

    if args.json:
        print(json.dumps({"models": rows, "missing_featured": missing}, indent=2))
        return 0

    print(f"Groq: {len(active)} model active, {len(chat_ids)} dùng được cho chat\n")
    for row in rows:
        mark = "*" if row["featured"] else " "
        print(f" {mark} {row['id']:<28} ctx={row['context_window'] or '?':<7} "
              f"{'light' if row.get('light') else '     '} {row.get('probe', '')}  {row.get('note', '')}")
    skipped = sorted(set(active) - set(chat_ids))
    print(f"\nBỏ qua (không phải chat): {', '.join(skipped)}")
    if missing:
        print(f"CẢNH BÁO — model nổi bật không còn trên Groq: {', '.join(missing)}")
    if not any(m.startswith("meta-llama/llama-3") or m.startswith("llama-") for m in chat_ids):
        print("Lưu ý: Groq hiện không có Llama chat model cho key này; dùng Llama qua Ollama/Kaggle.")
    light = [r["id"] for r in rows if r.get("light")]
    print(f"\nĐề xuất model nhẹ: {', '.join(light) or '(không có)'}")

    if args.ollama:
        check_ollama_registry()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
