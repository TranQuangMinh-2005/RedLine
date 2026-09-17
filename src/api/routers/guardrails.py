"""Xem nội dung guardrail, cấu hình Llama Guard và so sánh nguyên nhân từ chối.

- GET  /config/guardrails            luật/pattern/system prompt theo profile (canary đã ẩn)
- GET  /config/llama-guard           cấu hình chốt Llama Guard
- POST /config/llama-guard           bật/tắt, check_output, fail_mode, model
- POST /config/llama-guard/test      phân loại thử một đoạn text
- GET/POST /config/prompt-guard (+ /test)  chốt Prompt Guard 2 (injection)
- POST /chat/compare                 chạy lại prompt KHÔNG guardrail với các biến thể
                                     system prompt để biết model từ chối vì đâu
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents import target_agent
from src.config import ExecutionMode, get_settings
from src.guardrails import catalog, llama_guard, prompt_guard
from src.guardrails import state as defense_state
from src.guardrails.pipeline import looks_like_refusal
from src.guardrails.profiles import get_defense_profile
from src.logging_config import audit_event
from src.services import llm, llm_runtime
from src.services.rate_limit import RateLimitExceeded, TokenBudgetExceeded, roe_budget

router = APIRouter(tags=["guardrails"])

CompareVariant = Literal["no_system_prompt", "no_hardening", "active_prompt"]
VARIANT_LABELS = {
    "no_system_prompt": "Không system prompt (model gốc)",
    "no_hardening": "System prompt cơ bản, không hardening",
    "active_prompt": "System prompt của profile hiện hành",
}


def _require_trace_enabled() -> None:
    if not get_settings().GUARDRAIL_TRACE_ENABLED:
        raise HTTPException(status_code=404, detail="guardrail trace is disabled")


@router.get("/config/guardrails")
def read_guardrails(mode: ExecutionMode = "agent") -> dict[str, Any]:
    _require_trace_enabled()
    return {"active_profile": defense_state.get_active_name(), "mode": mode, **catalog.build_catalog(mode)}


class LlamaGuardUpdate(BaseModel):
    enabled: bool | None = None
    check_output: bool | None = None
    fail_mode: Literal["closed", "open"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._/:-]+$")


class LlamaGuardTest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    reply: str | None = Field(default=None, max_length=8000)


def _guard_state() -> dict[str, Any]:
    settings = get_settings()
    return {
        **llama_guard.public_config(),
        "target_config_hash": settings.target_config_hash_for(defense_state.get_active_name()),
    }


@router.get("/config/llama-guard")
def read_llama_guard() -> dict[str, Any]:
    return _guard_state()


@router.post("/config/llama-guard")
def update_llama_guard(req: LlamaGuardUpdate) -> dict[str, Any]:
    previous, current = llama_guard.update_config(**req.model_dump())
    audit_event(
        "llama_guard_config_changed", request_id=str(uuid4()),
        previous_enabled=previous.enabled, enabled=current.enabled,
        check_output=current.check_output, fail_mode=current.fail_mode, model=current.model,
    )
    return _guard_state()


@router.post("/config/llama-guard/test")
def test_llama_guard(req: LlamaGuardTest) -> dict[str, Any]:
    config = llama_guard.get_config()
    messages = [{"role": "user", "content": req.text}]
    if req.reply:
        messages.append({"role": "assistant", "content": req.reply})
    verdict = llama_guard.classify(messages, "output" if req.reply else "input", config)
    return {"model": config.model, "base_url": config.base_url, **verdict.as_dict()}


class PromptGuardUpdate(BaseModel):
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=0.01, le=0.99)
    check_rag: bool | None = None
    fail_mode: Literal["closed", "open"] | None = None


class PromptGuardTest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


def _prompt_guard_state() -> dict[str, Any]:
    return {
        **prompt_guard.public_config(),
        "target_config_hash": get_settings().target_config_hash_for(defense_state.get_active_name()),
    }


@router.get("/config/prompt-guard")
def read_prompt_guard() -> dict[str, Any]:
    return _prompt_guard_state()


@router.post("/config/prompt-guard")
def update_prompt_guard(req: PromptGuardUpdate) -> dict[str, Any]:
    previous, current = prompt_guard.update_config(**req.model_dump())
    audit_event(
        "prompt_guard_config_changed", request_id=str(uuid4()),
        previous_enabled=previous.enabled, enabled=current.enabled, threshold=current.threshold,
        check_rag=current.check_rag, fail_mode=current.fail_mode,
    )
    return _prompt_guard_state()


@router.post("/config/prompt-guard/test")
def test_prompt_guard(req: PromptGuardTest) -> dict[str, Any]:
    config = prompt_guard.get_config()
    try:
        scores, latency = prompt_guard.score_texts([req.text], config)
    except RuntimeError as exc:
        return {"model": config.model, "url": config.url, "score": None, "error": str(exc)}
    return {"model": config.model, "url": config.url, "score": scores[0], "threshold": config.threshold,
            "malicious": scores[0] >= config.threshold, "latency_s": latency, "error": None}


class CompareRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: ExecutionMode = "agent"
    variants: list[CompareVariant] = Field(
        default_factory=lambda: ["no_system_prompt", "no_hardening"], min_length=1, max_length=3
    )


@router.post("/chat/compare")
def compare_refusal(req: CompareRequest) -> dict[str, Any]:
    """Gửi cùng prompt tới model với các biến thể system prompt, KHÔNG qua guardrail code.

    Không có tool, không lưu session. Canary trong câu trả lời được ẩn.
    """
    _require_trace_enabled()
    settings = get_settings()
    if settings.ROE_KILL_SWITCH:
        raise HTTPException(status_code=503, detail="kill-switch active")
    active = defense_state.get_active_profile()
    results = []
    for variant in dict.fromkeys(req.variants):
        try:
            roe_budget.begin_request(
                settings.SCENARIO_CUSTOMER_ID,
                max_requests_per_minute=settings.ROE_MAX_REQUESTS_PER_MIN,
                max_tokens_total=settings.ROE_MAX_TOKENS_TOTAL,
            )
        except (RateLimitExceeded, TokenBudgetExceeded) as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        messages: list[dict[str, Any]] = []
        if variant != "no_system_prompt":
            profile = get_defense_profile("none") if variant == "no_hardening" else active
            messages.append({"role": "system",
                             "content": target_agent.build_system_prompt(profile=profile, mode=req.mode)})
        messages.append({"role": "user", "content": req.message})
        try:
            # Reasoning model (gpt-oss) cần nhiều token; 1024 dễ bị cắt thành câu trả lời rỗng.
            result = llm.chat(messages, max_tokens=4096)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM error: {llm.summarize_error(exc)}") from exc
        roe_budget.record_tokens(settings.SCENARIO_CUSTOMER_ID, int(result.get("total_tokens", 0)))
        text = catalog.redact_canary(result["text"])
        results.append({
            "variant": variant,
            "label": VARIANT_LABELS[variant],
            "reply": text,
            "refusal": looks_like_refusal(result["text"]),
            "empty": not result["text"].strip(),
            "finish_reason": result.get("finish_reason"),
            "canary_leaked": target_agent.leaked_canary(result["text"]),
            "model": result.get("model"),
            "total_tokens": result.get("total_tokens", 0),
            "latency_s": result.get("latency_s", 0),
        })
    audit_event("refusal_compare", request_id=str(uuid4()), variants=[r["variant"] for r in results],
                refusals=[r["refusal"] for r in results])
    return {"model": llm_runtime.active_model(), "active_profile": active.name, "results": results,
            "note": "Không tool, không guardrail code; phát hiện từ chối là heuristic."}
