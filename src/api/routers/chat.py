"""Stateful chat HTTP endpoint."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from src.agents import target_agent
from src.agents.session import InMemorySessionStore, SessionLimitError
from src.api.schemas import ChatRequest, ChatResponse
from src.config import get_settings
from src.guardrails import pipeline
from src.guardrails import state as defense_state
from src.logging_config import audit_event, reset_request_context, set_request_context
from src.services.rate_limit import RateLimitExceeded, TokenBudgetExceeded, roe_budget

router = APIRouter()
session_store = InMemorySessionStore(max_messages=50)


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(req: ChatRequest) -> ChatResponse:
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

    session_id = req.session_id or str(uuid4())
    request_id = str(uuid4())
    profile = defense_state.get_active_profile()
    token = set_request_context(request_id, session_id)
    audit_event(
        "request_received",
        request_id=request_id,
        session_id=session_id,
        message_length=len(req.message),
        mode=req.mode,
    )
    try:
        state = session_store.create_session(session_id)
        audit_event("session_loaded", request_id=request_id, session_id=session_id, history_messages=len(state.messages))
        state = session_store.append_message(session_id, "user", req.message)
        message_history = [message.as_dict() for message in state.messages]
        outcome = pipeline.run_turn(
            message_history, profile=profile, mode=req.mode, request_id=request_id, started=started
        )
        session_store.append_message(session_id, "assistant", outcome.reply)
        response = ChatResponse(
            mode=req.mode,
            session_id=session_id,
            reply=outcome.reply,
            model=outcome.model,
            latency_s=outcome.latency_s,
            total_tokens=outcome.total_tokens,
            canary_leaked=outcome.delivered_canary_detected,
            raw_canary_detected=outcome.raw_canary_detected,
            delivered_canary_detected=outcome.delivered_canary_detected,
            defense_profile=profile.name,
            target_config_hash=settings.target_config_hash_for(profile.name),
            guardrail_blocked=outcome.guardrail_blocked,
            guardrail_actions=outcome.guardrail_actions,
            trace=outcome.trace if req.include_trace and settings.GUARDRAIL_TRACE_ENABLED else None,
        )
        if outcome.total_tokens:
            roe_budget.record_tokens(settings.SCENARIO_CUSTOMER_ID, response.total_tokens)
        audit_event("response_sent", request_id=request_id, session_id=session_id, status_code=200, latency_s=round(time.monotonic() - started, 3))
        return response
    except SessionLimitError as exc:
        audit_event("request_failed", request_id=request_id, session_id=session_id, error_type="session_limit")
        raise HTTPException(status_code=429, detail="session message limit reached") from exc
    except HTTPException:
        raise
    except Exception as exc:
        audit_event("request_failed", request_id=request_id, session_id=session_id, error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"LLM error: {target_agent.llm.summarize_error(exc)}") from exc
    finally:
        reset_request_context(token)
