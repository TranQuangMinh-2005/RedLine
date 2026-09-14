"""Load and validate the switchable guardrail profiles."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

DefenseProfileName = Literal["none", "basic", "strict"]
VALID_PROFILE_NAMES = frozenset({"none", "basic", "strict"})


@dataclass(frozen=True)
class DefenseProfile:
    """Features enabled for one immutable benchmark profile."""

    name: DefenseProfileName
    input_filter: bool
    output_filter: bool
    prompt_hardening: bool
    canary_check: bool


@lru_cache(maxsize=1)
def _load_config() -> dict:
    import yaml

    config_path = Path(__file__).with_name("config.yml")
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or not isinstance(config.get("profiles"), dict):
        raise RuntimeError("guardrails/config.yml must contain a profiles mapping")
    return config


def get_defense_profile(name: str | None = None) -> DefenseProfile:
    """Return a validated profile from config.yml."""

    config = _load_config()
    selected = name or config.get("active_profile", "none")
    if selected not in VALID_PROFILE_NAMES:
        valid = ", ".join(sorted(VALID_PROFILE_NAMES))
        raise ValueError(f"unknown DEFENSE_PROFILE={selected!r}; expected one of: {valid}")

    raw = config["profiles"].get(selected)
    required = {"input_filter", "output_filter", "prompt_hardening", "canary_check"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise RuntimeError(f"guardrail profile {selected!r} must define exactly {sorted(required)}")
    if any(not isinstance(raw[key], bool) for key in required):
        raise RuntimeError(f"guardrail profile {selected!r} values must be booleans")

    return DefenseProfile(
        name=cast(DefenseProfileName, selected),
        input_filter=raw["input_filter"],
        output_filter=raw["output_filter"],
        prompt_hardening=raw["prompt_hardening"],
        canary_check=raw["canary_check"],
    )
