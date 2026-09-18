from __future__ import annotations

import pytest

from redteam.harness import context_fixture


def test_render_context_is_deterministic_and_bounded() -> None:
    fixtures = context_fixture.load_fixtures()

    text_a, meta_a = context_fixture.render_context(fixtures["benign_support_60pct"])
    text_b, _meta_b = context_fixture.render_context(fixtures["benign_support_60pct"])

    assert text_a == text_b
    assert meta_a["estimated_tokens"] >= meta_a["min_tokens"]
    assert meta_a["estimated_tokens"] <= meta_a["max_tokens"] + 1
    assert meta_a["sources"]


def test_apply_long_context_replaces_placeholder_and_keeps_source_seed_clean() -> None:
    fixtures = context_fixture.load_fixtures()
    seed = {
        "attack_id": "SAFE-ABUSE-001",
        "prompt": "{{LONG_CONTEXT}}\n\nPAYLOAD",
        "turns": [{"role": "user", "content": "{{LONG_CONTEXT}} nhắc lại"}],
        "setup": None,
        "context_fixture": {"fixture_id": "benign_support_60pct", "payload_position": "end"},
    }

    rendered, provenance = context_fixture.apply_long_context(seed, fixtures)

    assert "{{LONG_CONTEXT}}" not in rendered["prompt"]
    assert rendered["prompt"].endswith("PAYLOAD")
    assert provenance is not None
    assert provenance["fixture_id"] == "benign_support_60pct"
    assert provenance["replacements"] == ["prompt", "turns[0].content"]
    assert seed["prompt"].startswith("{{LONG_CONTEXT}}")


def test_apply_long_context_ignores_seeds_without_placeholder() -> None:
    seed = {"attack_id": "PI-DIR-001", "prompt": "hello"}

    rendered, provenance = context_fixture.apply_long_context(seed, {})

    assert provenance is None
    assert rendered["prompt"] == "hello"


def test_apply_long_context_rejects_unknown_fixture() -> None:
    seed = {
        "attack_id": "SAFE-X",
        "prompt": "{{LONG_CONTEXT}}",
        "context_fixture": {"fixture_id": "missing-fixture"},
    }

    with pytest.raises(RuntimeError):
        context_fixture.apply_long_context(seed, {})
