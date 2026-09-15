"""FastAPI entrypoint của TARGET (W1 task 1.4, 2.1).

- /health: cho Docker healthcheck (docker-compose gọi endpoint này)
- /chat: endpoint hội thoại stateful (session_id -> lịch sử multi-turn)

Chạy local:
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
Hay trong Docker:
    make up
"""

from __future__ import annotations

import time
from fastapi import FastAPI

from guardrails.profiles import get_defense_profile
from src.api.routers.chat import router as chat_router
from src.api.routers.openai_compat import router as openai_router
from src.config import get_settings
from src.logging_config import configure_logging

app = FastAPI(
    title="RedLine Target — Customer Assistant",
    version="0.1.0-w1",
    description="Ứng dụng LLM mục tiêu CỐ Ý có lỗ hổng (sandbox, được phép tấn công).",
)

settings = get_settings()
defense_profile = get_defense_profile(settings.DEFENSE_PROFILE)

@app.get("/health")
def health() -> dict:
    """Healthcheck cho Docker — không cần LLM, luôn trả về nhanh."""
    return {
        "status": "ok",
        "time": time.time(),
        "defense_profile": defense_profile.name,
        "target_config_hash": settings.target_config_hash,
    }


app.include_router(chat_router)
app.include_router(openai_router)
configure_logging()
