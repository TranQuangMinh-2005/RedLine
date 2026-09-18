"""HTTP request and response contracts for the target."""

from typing import Any

from pydantic import BaseModel, Field

from src.config import ExecutionMode


class ChatRequest(BaseModel):
    mode: ExecutionMode = "agent"
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    # Trả pipeline guardrail (UI debug). Bỏ qua nếu GUARDRAIL_TRACE_ENABLED=false.
    include_trace: bool = False


class ChatResponse(BaseModel):
    mode: ExecutionMode = "agent"
    session_id: str
    reply: str
    model: str
    provider: str | None = None
    provider_slot: str | None = None
    provider_attempts: list[str] = Field(default_factory=list)
    latency_s: float
    total_tokens: int
    canary_leaked: bool = False
    raw_canary_detected: bool = False
    delivered_canary_detected: bool = False
    defense_profile: str
    target_config_hash: str
    guardrail_blocked: bool = False
    guardrail_actions: list[str] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
