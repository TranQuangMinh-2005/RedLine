"""OpenAI-compatible endpoints (/v1/chat/completions, /v1/models, /).

Cho phép kết nối RedLine Target Agent từ bất kỳ OpenAI client,
LangChain, LlamaIndex, OpenWebUI hoặc benchmarking harness nào.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.guardrails.input_filter import BLOCKED_INPUT_REPLY, inspect_messages
from src.guardrails.output_filter import inspect_output
from src.guardrails import state as defense_state
from src.agents import target_agent
from src.config import ExecutionMode, get_settings
from src.logging_config import audit_event, reset_request_context, set_request_context
from src.services.rate_limit import RateLimitExceeded, TokenBudgetExceeded, roe_budget

router = APIRouter()


class OpenAIMessage(BaseModel):
    role: str
    content: str | None = ""
    name: str | None = None


class OpenAIChatRequest(BaseModel):
    mode: ExecutionMode = "agent"
    model: str | None = None
    messages: list[OpenAIMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool | None = False
    session_id: str | None = None


@router.get("/")
def root() -> dict[str, Any]:
    """Root endpoint hiển thị thông tin target."""
    settings = get_settings()
    profile = defense_state.get_active_profile()
    return {
        "name": "RedLine Target — Customer Assistant",
        "version": "0.1.0",
        "status": "online",
        "model": settings.LLM_MODEL,
        "defense_profile": profile.name,
        "endpoints": {
            "health": "/health",
            "chat_native": "/chat",
            "openai_chat_completions": "/v1/chat/completions",
            "openai_models": "/v1/models",
        },
    }


@router.get("/v1/models")
@router.get("/chat/v1/models")
@router.get("/models")
def list_models() -> dict[str, Any]:
    """Danh sách mô hình chuẩn OpenAI format."""
    settings = get_settings()
    active_model = settings.LLM_MODEL
    models = [active_model, "qwen2.5:14b", "qwen3.8-27b", "default"]

    seen = set()
    unique_models = [m for m in models if not (m in seen or seen.add(m))]
    now = int(time.time())

    return {
        "object": "list",
        "data": [
            {
                "id": m,
                "object": "model",
                "created": now,
                "owned_by": "redline",
                "permission": [],
                "root": m,
                "parent": None,
            }
            for m in unique_models
        ],
    }


@router.get("/v1/models/{model_id}")
@router.get("/chat/v1/models/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    """Chi tiết một model chuẩn OpenAI format."""
    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "redline",
        "permission": [],
        "root": model_id,
        "parent": None,
    }


@router.post("/v1/chat/completions")
@router.post("/chat/v1/chat/completions")
def chat_completions(req: OpenAIChatRequest) -> Any:
    """Endpoint OpenAI chat/completions chuẩn gọi vào RedLine RAG Agent."""
    started = time.monotonic()
    settings = get_settings()
    if settings.ROE_KILL_SWITCH:
        raise HTTPException(status_code=503, detail="kill-switch active")
    try:
        roe_budget.begin_request(
            settings.SCENARIO_CUSTOMER_ID,
            max_requests_per_minute=settings.ROE_MAX_REQUESTS_PER_MIN,
            max_tokens_total=settings.ROE_MAX_TOKENS_TOTAL,
        )
    except (RateLimitExceeded, TokenBudgetExceeded) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    # Lọc lịch sử hội thoại
    chat_messages: list[dict[str, Any]] = []
    last_user_message = ""
    for m in req.messages:
        if m.role == "user":
            chat_messages.append({"role": "user", "content": m.content or ""})
            last_user_message = m.content or ""
        elif m.role == "assistant":
            chat_messages.append({"role": "assistant", "content": m.content or ""})

    if not chat_messages:
        raise HTTPException(status_code=400, detail="messages list cannot be empty")

    session_id = req.session_id or str(uuid4())
    request_id = str(uuid4())
    profile = defense_state.get_active_profile()
    token = set_request_context(request_id, session_id)
    audit_event(
        "request_received",
        request_id=request_id,
        session_id=session_id,
        message_length=len(last_user_message),
        mode=req.mode,
    )

    try:
        # 1. Guardrail input
        input_decision = inspect_messages(chat_messages, profile)
        if input_decision.blocked:
            reply = BLOCKED_INPUT_REPLY
            total_tokens = 0
            model_name = req.model or settings.LLM_MODEL
            canary_leaked = False
            guardrail_blocked = True
            guardrail_actions = list(input_decision.actions)
        else:
            # 2. Gọi RAG Target Agent
            result = target_agent.respond(chat_messages, defense_profile=profile, mode=req.mode)
            output_decision = inspect_output(
                result["text"],
                profile,
                canary=settings.CANARY_TOKEN,
                allowed_customer_id=settings.SCENARIO_CUSTOMER_ID,
            )
            reply = output_decision.text
            total_tokens = int(result.get("total_tokens", 0))
            model_name = result.get("model", req.model or settings.LLM_MODEL)
            canary_leaked = target_agent.leaked_canary(reply)
            guardrail_blocked = output_decision.filtered
            guardrail_actions = list(output_decision.actions)

        roe_budget.record_tokens(settings.SCENARIO_CUSTOMER_ID, total_tokens)

        latency = round(time.monotonic() - started, 3)
        created_ts = int(time.time())
        completion_id = f"chatcmpl-{uuid4().hex[:24]}"

        audit_event(
            "response_sent",
            request_id=request_id,
            session_id=session_id,
            status_code=200,
            latency_s=latency,
        )

        # 3. Hỗ trợ Server-Sent Events khi client yêu cầu stream=True
        if req.stream:
            def event_generator():
                # Chunk 1: thông báo role
                chunk1 = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk1, ensure_ascii=False)}\n\n"

                # Chunk 2: trả nội dung text
                chunk2 = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": reply},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n"

                # Chunk 3: kết thúc
                chunk3 = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk3, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        # 4. Trả về JSON chuẩn OpenAI format
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": max(1, total_tokens // 2),
                "completion_tokens": max(1, total_tokens - (total_tokens // 2)),
                "total_tokens": total_tokens,
            },
            "system_fingerprint": settings.target_config_hash_for(profile.name),
            "redline": {
                "mode": req.mode,
                "session_id": session_id,
                "canary_leaked": canary_leaked,
                "defense_profile": profile.name,
                "guardrail_blocked": guardrail_blocked,
                "guardrail_actions": guardrail_actions,
                "latency_s": latency,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        audit_event("request_failed", request_id=request_id, session_id=session_id, error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"LLM error: {type(exc).__name__}") from exc
    finally:
        reset_request_context(token)
