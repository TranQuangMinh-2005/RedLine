"""FastAPI entrypoint của TARGET (W1 task 1.4, 2.1).

- /health: cho Docker healthcheck (docker-compose gọi endpoint này)
- /chat: endpoint hội thoại stateful (session_id -> lịch sử multi-turn)
- /config/defense-profile: đổi guardrail mode khi đang chạy (W5 / demo)

Chạy local:
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
Hay trong Docker:
    make up
"""

from __future__ import annotations

import time
from fastapi import FastAPI

from src.api.routers.chat import router as chat_router
from src.api.routers.config import router as config_router
from src.api.routers.openai_compat import router as openai_router
from src.api.routers.rag import router as rag_router
from src.config import get_settings
from src.logging_config import configure_logging
from src.guardrails import state as defense_state

app = FastAPI(
    title="RedLine Target — Customer Assistant",
    version="0.1.0-w1",
    description="Ứng dụng LLM mục tiêu CỐ Ý có lỗ hổng (sandbox, được phép tấn công).",
)

settings = get_settings()


@app.get("/health")
def health() -> dict:
    """Healthcheck cho Docker — không cần LLM, luôn trả về nhanh.

    `defense_profile` đọc từ runtime state nên phản ánh mode hiện hành
    (có thể đã đổi qua POST /config/defense-profile).
    """
    active = defense_state.get_active_name()
    return {
        "status": "ok",
        "time": time.time(),
        "defense_profile": active,
        "target_config_hash": settings.target_config_hash,
    }


app.include_router(chat_router)
app.include_router(config_router)
app.include_router(openai_router)
app.include_router(rag_router)
configure_logging()
