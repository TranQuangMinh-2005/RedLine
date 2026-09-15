"""Stateful chat HTTP endpoint."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from guardrails.input_filter import BLOCKED_INPUT_REPLY, inspect_input
from guardrails.output_filter import inspect_output
from guardrails.profiles import get_defense_profile
from src.agents import target_agent
from src.agents.state_store import InMemorySessionStore, SessionLimitError
from src.config import get_settings
from src.logging_config import audit_event, reset_request_context, set_request_context
from src.models.schemas import ChatRequest, ChatResponse

router = APIRouter()
session_store = InMemorySessionStore(max_messages=50)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    started = time.monotonic()
    settings = get_settings()
    if settings.ROE_KILL_SWITCH:
        raise HTTPException(status_code=503, detail="kill-switch active")

    session_id = req.session_id or str(uuid4())
    request_id = str(uuid4())
    profile = get_defense_profile(settings.DEFENSE_PROFILE)
    token = set_request_context(request_id, session_id)
    audit_event("request_received", request_id=request_id, session_id=session_id, message_length=len(req.message))
    try:
        state = session_store.create_session(session_id)
        audit_event("session_loaded", request_id=request_id, session_id=session_id, history_messages=len(state.messages))
        state = session_store.append_message(session_id, "user", req.message)
        input_decision = inspect_input(req.message, profile)
        if input_decision.blocked:
            reply = BLOCKED_INPUT_REPLY
            session_store.append_message(session_id, "assistant", reply)
            response = ChatResponse(
                session_id=session_id,
                reply=reply,
                model=settings.LLM_MODEL,
                latency_s=round(time.monotonic() - started, 3),
                total_tokens=0,
                canary_leaked=False,
                defense_profile=profile.name,
                target_config_hash=settings.target_config_hash,
                guardrail_blocked=True,
                guardrail_actions=list(input_decision.actions),
            )
        else:
            result = target_agent.respond([message.as_dict() for message in state.messages], defense_profile=profile)
            output_decision = inspect_output(result["text"], profile, canary=settings.CANARY_TOKEN)
            reply = output_decision.text
            session_store.append_message(session_id, "assistant", reply)
            response = ChatResponse(
                session_id=session_id,
                reply=reply,
                model=result["model"],
                latency_s=float(result["latency_s"]),
                total_tokens=int(result["total_tokens"]),
                canary_leaked=target_agent.leaked_canary(reply),
                defense_profile=profile.name,
                target_config_hash=settings.target_config_hash,
                guardrail_blocked=output_decision.filtered,
                guardrail_actions=list(output_decision.actions),
            )
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
