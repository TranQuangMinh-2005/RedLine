import pytest

from src.guardrails.profiles import get_defense_profile


@pytest.mark.parametrize(
    (
        "name",
        "input_filter",
        "output_filter",
        "prompt_hardening",
        "canary_check",
        "tool_authorization",
        "rag_filter",
        "action_policy",
    ),
    [
        ("none", False, False, False, False, False, False, False),
        ("basic", True, False, True, True, True, False, False),
        ("strict", True, True, True, True, True, True, True),
    ],
)
def test_profile_flags(
    name: str,
    input_filter: bool,
    output_filter: bool,
    prompt_hardening: bool,
    canary_check: bool,
    tool_authorization: bool,
    rag_filter: bool,
    action_policy: bool,
) -> None:
    profile = get_defense_profile(name)
    assert profile.input_filter is input_filter
    assert profile.output_filter is output_filter
    assert profile.prompt_hardening is prompt_hardening
    assert profile.canary_check is canary_check
    assert profile.tool_authorization is tool_authorization
    assert profile.rag_filter is rag_filter
    assert profile.action_policy is action_policy


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown DEFENSE_PROFILE"):
        get_defense_profile("unsupported")
