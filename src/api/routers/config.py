"""Endpoint cấu hình runtime cho target (đổi guardrail mode khi đang chạy)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.guardrails.profiles import VALID_PROFILE_NAMES, get_defense_profile
from src.config import get_settings
from src.logging_config import audit_event
from src.guardrails import state as defense_state

router = APIRouter(tags=["config"])


class DefenseProfileRequest(BaseModel):
    profile: str


@router.get("/config/defense-profile")
def read_defense_profile() -> dict:
    """Trả mode hiện hành + danh sách mode hợp lệ + mặc định trong .env."""
    settings = get_settings()
    active = defense_state.get_active_name()
    profile = get_defense_profile(active)
    options = []
    for name in sorted(VALID_PROFILE_NAMES):
        p = get_defense_profile(name)
        options.append(
            {
                "name": p.name,
                "input_filter": p.input_filter,
                "output_filter": p.output_filter,
                "prompt_hardening": p.prompt_hardening,
                "canary_check": p.canary_check,
            }
        )
    return {
        "active": active,
        "default_from_env": settings.DEFENSE_PROFILE,
        "target_config_hash": settings.target_config_hash,
        "capabilities": {
            "input_filter": profile.input_filter,
            "output_filter": profile.output_filter,
            "prompt_hardening": profile.prompt_hardening,
            "canary_check": profile.canary_check,
        },
        "options": options,
    }


@router.post("/config/defense-profile")
def update_defense_profile(req: DefenseProfileRequest) -> dict:
    """Đổi guardrail mode ngay lập tức (không cần restart container).

    Dùng cho demo W5: chuyển none <-> basic <-> strict giữa các lô tấn công.
    """
    requested = (req.profile or "").strip().lower()
    try:
        previous, active = defense_state.set_active_name(requested)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    profile = get_defense_profile(active)
    audit_event(
        "defense_profile_changed",
        request_id=str(uuid4()),
        previous=previous,
        active=active,
        input_filter=profile.input_filter,
        output_filter=profile.output_filter,
    )
    return {
        "previous": previous,
        "active": active,
        "capabilities": {
            "input_filter": profile.input_filter,
            "output_filter": profile.output_filter,
            "prompt_hardening": profile.prompt_hardening,
            "canary_check": profile.canary_check,
        },
    }
