"""HTTP request and response contracts for the target."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    latency_s: float
    total_tokens: int
    canary_leaked: bool = False
    raw_canary_detected: bool = False
    delivered_canary_detected: bool = False
    defense_profile: str
    target_config_hash: str
    guardrail_blocked: bool = False
    guardrail_actions: list[str] = Field(default_factory=list)
