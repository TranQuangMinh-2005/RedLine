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
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from guardrails.input_filter import BLOCKED_INPUT_REPLY, inspect_input
from guardrails.output_filter import inspect_output
from guardrails.profiles import get_defense_profile
from src.agents import target_agent
from src.config import get_settings

app = FastAPI(
    title="RedLine Target — Customer Assistant",
    version="0.1.0-w1",
    description="Ứng dụng LLM mục tiêu CỐ Ý có lỗ hổng (sandbox, được phép tấn công).",
)

settings = get_settings()
defense_profile = get_defense_profile(settings.DEFENSE_PROFILE)

# Lưu trữ session trong bộ nhớ (W1 đơn giản; W2 sẽ chuyển sang DB/REDIS)
# key: session_id -> list[{"role", "content"}]
SESSIONS: dict[str, list[dict[str, str]]] = {}
SESSION_MAX_TURNS = 50  # chặn session quá dài


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    latency_s: float
    total_tokens: int
    canary_leaked: bool = False
    defense_profile: str
    target_config_hash: str
    guardrail_blocked: bool = False
    guardrail_actions: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict:
    """Healthcheck cho Docker — không cần LLM, luôn trả về nhanh."""
    return {
        "status": "ok",
        "time": time.time(),
        "defense_profile": defense_profile.name,
        "target_config_hash": settings.target_config_hash,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Gửi 1 message, trả về reply. Giữ session state giữa các turn.

    - Không cần session_id -> tạo mới
    - Có session_id -> nối vào lịch sử, trả về nguyên session
    """
    t0 = time.time()

    if settings.ROE_KILL_SWITCH:
        raise HTTPException(status_code=503, detail="kill-switch active — hệ thống đang dừng khẩn cấp")

    session_id = req.session_id or str(uuid.uuid4())
    hist = SESSIONS.get(session_id, [])

    # Rate limit đơn giản: chặn session dài (W3 sẽ thay bằng rate_limit.py đầy đủ)
    if len(hist) >= SESSION_MAX_TURNS:
        raise HTTPException(status_code=429, detail="session quá dài — tạo session mới")

    hist.append({"role": "user", "content": req.message})

    input_decision = inspect_input(req.message, defense_profile)
    if input_decision.blocked:
        reply = BLOCKED_INPUT_REPLY
        hist.append({"role": "assistant", "content": reply})
        SESSIONS[session_id] = hist[-SESSION_MAX_TURNS:]
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            model=req.model or settings.LLM_MODEL,
            latency_s=round(time.time() - t0, 3),
            total_tokens=0,
            canary_leaked=False,
            defense_profile=defense_profile.name,
            target_config_hash=settings.target_config_hash,
            guardrail_blocked=True,
            guardrail_actions=list(input_decision.actions),
        )

    try:
        result = target_agent.respond(
            hist,
            model=req.model,
            defense_profile=defense_profile,
        )
    except Exception as exc:  # noqa: BLE001 — lỗi LLM không được làm sập API
        raise HTTPException(status_code=502, detail=f"LLM error: {target_agent.llm.summarize_error(exc)}") from exc

    output_decision = inspect_output(
        result["text"],
        defense_profile,
        canary=settings.CANARY_TOKEN,
    )
    reply = output_decision.text
    hist.append({"role": "assistant", "content": reply})

    # Giới hạn mỗi session 50 turn -> dùng slice thay vì xóa
    SESSIONS[session_id] = hist[-SESSION_MAX_TURNS:]

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        model=result["model"],
        latency_s=result["latency_s"],
        total_tokens=result["total_tokens"],
        canary_leaked=target_agent.leaked_canary(reply),
        defense_profile=defense_profile.name,
        target_config_hash=settings.target_config_hash,
        guardrail_blocked=output_decision.filtered,
        guardrail_actions=list(output_decision.actions),
    )
