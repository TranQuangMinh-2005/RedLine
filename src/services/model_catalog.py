"""Danh mục model nổi bật cho UI chọn model.

- Groq: đã kiểm tra bằng `scripts/model_check.py` (list + probe tool calling).
- Ollama: tag đã xác minh trên registry.ollama.ai; size là dung lượng tải (GB).
  Kaggle T4 x2 có ~15 GB VRAM mỗi GPU -> ưu tiên model <= 14 GB.

Model không có trong danh mục vẫn chọn được nếu endpoint trả về trong /v1/models.
"""

from __future__ import annotations

from typing import Any

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
# Model free mặc định cho OpenRouter: đã kiểm tra tiếng Việt + tool calling (23s chat / 8s tool).
# Tài khoản chưa mua credit chỉ gọi được model đuôi ":free" và tối đa 50 request/ngày.
DEFAULT_OPENROUTER_MODEL = "nex-agi/nex-n2.5-pro:free"

GROQ_FEATURED: list[dict[str, Any]] = [
    {"id": "openai/gpt-oss-20b", "family": "gpt-oss", "label": "GPT-OSS 20B",
     "tools": True, "light": True, "note": "Mặc định — nhanh, rẻ, tool calling ổn định"},
    {"id": "qwen/qwen3.8-27b", "family": "qwen", "label": "Qwen3.8 27B",
     "tools": True, "light": False, "note": "Qwen mới nhất trên Groq"},
    {"id": "openai/gpt-oss-120b", "family": "gpt-oss", "label": "GPT-OSS 120B",
     "tools": True, "light": False, "note": "Mạnh hơn, chậm/đắt hơn 20B"},
]

# Model Groq không dùng cho chat (audio, guard classifier, compound system).
GROQ_NON_CHAT_PREFIXES = (
    "whisper", "canopylabs/", "meta-llama/llama-prompt-guard", "openai/gpt-oss-safeguard",
    "groq/compound", "allam-",
)

# OpenRouter: 444 model. Danh sách nổi bật = model free có tool calling (đã đo) + vài model
# trả phí rất rẻ dùng được khi tài khoản đã nạp credit.
OPENROUTER_FEATURED: list[dict[str, Any]] = [
    {"id": "nex-agi/nex-n2.5-pro:free", "family": "nex", "label": "Nex N2.5 Pro (free)",
     "tools": True, "light": True, "note": "Miễn phí — đã đo: tiếng Việt tốt, tool calling OK"},
    {"id": "nex-agi/nex-n2.5-mini:free", "family": "nex", "label": "Nex N2.5 Mini (free)",
     "tools": True, "light": True, "note": "Miễn phí, nhỏ hơn bản Pro"},
    {"id": "google/gemma-4-31b-it:free", "family": "gemma", "label": "Gemma 4 31B (free)",
     "tools": True, "light": True, "note": "Miễn phí — pool dùng chung, hay gặp 429"},
    {"id": "nvidia/nemotron-3.5-lightning:free", "family": "nemotron", "label": "Nemotron 3.5 Lightning (free)",
     "tools": True, "light": False, "note": "Miễn phí nhưng chậm (~60-105s) và lẫn suy luận vào câu trả lời"},
    {"id": "openai/gpt-oss-20b", "family": "gpt-oss", "label": "GPT-OSS 20B",
     "tools": True, "light": True, "note": "Cần credit — cùng model đang dùng ở Groq, giá ~$0.03/1M token"},
    {"id": "openai/gpt-oss-120b", "family": "gpt-oss", "label": "GPT-OSS 120B",
     "tools": True, "light": False, "note": "Cần credit"},
    {"id": "meta-llama/llama-3.3-70b-instruct", "family": "llama", "label": "Llama 3.3 70B",
     "tools": True, "light": False, "note": "Cần credit — Llama có tool calling"},
    {"id": "qwen/qwen3-8b", "family": "qwen", "label": "Qwen3 8B",
     "tools": True, "light": True, "note": "Cần credit"},
]

OLLAMA_FEATURED: list[dict[str, Any]] = [
    {"id": "qwen3.5:4b", "family": "qwen", "label": "Qwen3.5 4B", "size_gb": 3.39,
     "tools": True, "light": True, "note": "Nhẹ, đề xuất mặc định cho Kaggle"},
    {"id": "qwen3.5:9b", "family": "qwen", "label": "Qwen3.5 9B", "size_gb": 6.59,
     "tools": True, "light": True, "note": "Cân bằng chất lượng/tốc độ"},
    {"id": "qwen3:4b", "family": "qwen", "label": "Qwen3 4B", "size_gb": 2.5,
     "tools": True, "light": True, "note": ""},
    {"id": "qwen3:8b", "family": "qwen", "label": "Qwen3 8B", "size_gb": 5.23,
     "tools": True, "light": True, "note": ""},
    {"id": "qwen2.5:7b", "family": "qwen", "label": "Qwen2.5 7B", "size_gb": 4.68,
     "tools": True, "light": True, "note": ""},
    {"id": "qwen2.5:14b", "family": "qwen", "label": "Qwen2.5 14B", "size_gb": 8.99,
     "tools": True, "light": False, "note": "Mặc định cũ của notebook Kaggle"},
    {"id": "gpt-oss:20b", "family": "gpt-oss", "label": "GPT-OSS 20B", "size_gb": 13.79,
     "tools": True, "light": False, "note": "Cùng model mặc định Groq; vừa 1 GPU T4"},
    {"id": "llama3.2:3b", "family": "llama", "label": "Llama 3.2 3B", "size_gb": 2.02,
     "tools": True, "light": True, "note": "Llama nhẹ nhất có tool calling"},
    {"id": "llama3.1:8b", "family": "llama", "label": "Llama 3.1 8B", "size_gb": 4.92,
     "tools": True, "light": True, "note": ""},
]


def is_groq_chat_model(model_id: str) -> bool:
    return not model_id.startswith(GROQ_NON_CHAT_PREFIXES)


def annotate(model_ids: list[str], featured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ghép danh sách model thực có trên endpoint với metadata nổi bật.

    Model nổi bật đứng trước theo thứ tự danh mục, phần còn lại sắp theo tên.
    """
    by_id = {row["id"]: row for row in featured}
    # Ollama trả "name:latest" khi tag mặc định; khớp cả hai dạng.
    def lookup(model_id: str) -> dict[str, Any] | None:
        return by_id.get(model_id) or by_id.get(model_id.removesuffix(":latest"))

    order = {row["id"]: i for i, row in enumerate(featured)}
    rows = []
    for model_id in dict.fromkeys(model_ids):
        meta = lookup(model_id)
        rows.append({**(meta or {}), "id": model_id, "featured": meta is not None})
    rows.sort(key=lambda r: (not r["featured"], order.get(r["id"], 0), r["id"]))
    return rows
