"""Render the long benign-context fixtures used by long-context seeds.

Assembly is deterministic: paragraphs are taken round-robin from the declared
corpus files until the fixture's minimum token target is reached, and never
beyond the maximum. The same rendered text is reused for every defense profile
so profile comparisons stay valid.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

LONG_CONTEXT_PLACEHOLDER = "{{LONG_CONTEXT}}"
DEFAULT_FIXTURES_PATH = Path("redteam/attacks/fixtures/long_contexts.yml")
DEFAULT_CORPUS_DIR = Path("data/rag/documents")
CHARS_PER_TOKEN = 4


def load_fixtures(path: str | Path = DEFAULT_FIXTURES_PATH) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fixtures = raw.get("fixtures") or {}
    if not isinstance(fixtures, dict):
        raise RuntimeError("long_contexts.yml must define a fixtures mapping")
    return fixtures


def _strip_front_matter(raw: str) -> str:
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end != -1:
            return raw[end + 4 :].lstrip("\r\n")
    return raw


def _paragraphs(path: Path) -> list[str]:
    raw = _strip_front_matter(path.read_text(encoding="utf-8"))
    return [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]


def render_context(
    fixture: dict[str, Any],
    *,
    corpus_dir: str | Path = DEFAULT_CORPUS_DIR,
) -> tuple[str, dict[str, Any]]:
    """Assemble benign paragraphs up to the fixture target size."""

    corpus_dir = Path(corpus_dir)
    separator = str(fixture.get("separator") or "\n\n")
    min_chars = max(1, int(fixture.get("min_tokens") or 3000)) * CHARS_PER_TOKEN
    max_chars = max(min_chars, int(fixture.get("max_tokens") or 8000) * CHARS_PER_TOKEN)
    sources = []
    for name in fixture.get("sources") or []:
        candidate = Path(str(name))
        if not candidate.exists():
            candidate = corpus_dir / str(name)
        sources.append(candidate)
    buckets = [(path.name, _paragraphs(path)) for path in sources if path.exists()]
    if not buckets:
        raise RuntimeError(f"no long-context sources available under {corpus_dir}")

    parts: list[str] = []
    used: set[str] = set()
    total = 0
    cursor = 0
    while total < min_chars:
        progressed = False
        for name, bucket in buckets:
            if not bucket:
                continue
            piece = bucket[cursor % len(bucket)]
            remaining = max_chars - total
            if remaining <= 0:
                break
            piece = piece[:remaining]
            parts.append(piece)
            used.add(name)
            total += len(piece) + len(separator)
            progressed = True
            if total >= min_chars or total >= max_chars:
                break
        if not progressed or total >= max_chars:
            break
        cursor += 1

    text = separator.join(parts).strip()
    metadata = {
        "estimated_tokens": total // CHARS_PER_TOKEN,
        "chars": len(text),
        "sources": sorted(used),
        "min_tokens": min_chars // CHARS_PER_TOKEN,
        "max_tokens": max_chars // CHARS_PER_TOKEN,
    }
    return text, metadata


def _replace_in_node(node: Any, context: str, path: str, replaced: list[str]) -> Any:
    if isinstance(node, str):
        if LONG_CONTEXT_PLACEHOLDER in node:
            replaced.append(path or "value")
            return node.replace(LONG_CONTEXT_PLACEHOLDER, context)
        return node
    if isinstance(node, dict):
        return {
            key: _replace_in_node(value, context, f"{path}.{key}" if path else str(key), replaced)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [
            _replace_in_node(value, context, f"{path}[{index}]", replaced)
            for index, value in enumerate(node)
        ]
    return node


def apply_long_context(
    seed: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    *,
    corpus_dir: str | Path = DEFAULT_CORPUS_DIR,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return a copy of the seed with the placeholder rendered, plus provenance."""

    if LONG_CONTEXT_PLACEHOLDER not in json.dumps(seed, ensure_ascii=False):
        return seed, None
    context_fixture = seed.get("context_fixture") or {}
    fixture_id = str(context_fixture.get("fixture_id") or "")
    fixture = fixtures.get(fixture_id)
    if fixture is None:
        raise RuntimeError(
            f"seed {seed.get('attack_id')} references unknown long-context fixture {fixture_id!r}"
        )
    context, metadata = render_context(fixture, corpus_dir=corpus_dir)
    replaced: list[str] = []
    rendered = _replace_in_node(copy.deepcopy(seed), context, "", replaced)
    provenance = {
        "fixture_id": fixture_id,
        "payload_position": context_fixture.get("payload_position"),
        "replacements": replaced,
        **metadata,
    }
    return rendered, provenance
