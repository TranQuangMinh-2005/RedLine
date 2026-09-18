#!/usr/bin/env python3
"""Tim kiem kho tri thuc ky thuat tan cong (OWASP / MITRE ATLAS / techniques).

Engine deterministic, chi dung stdlib. Vi du:

    python -m redteam.attacks.knowledge.search "prompt injection"
    python -m redteam.attacks.knowledge.search jailbreak
    python -m redteam.attacks.knowledge.search "role in prompt" --type technique
    python -m redteam.attacks.knowledge.search LLM01 --json
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

KNOWLEDGE_PATH = Path(__file__).with_name("knowledge_base.json")
SECTIONS: tuple[tuple[str, str], ...] = (
    ("owasp_llm_top10", "owasp"),
    ("atlas", "atlas"),
    ("techniques", "technique"),
)
ENTRY_TYPES = tuple(entry_type for _, entry_type in SECTIONS)
SUMMARY_FIELDS = ("summary", "how_it_works", "detection", "mitigation")
PUNCTUATION = ".,;:!?()[]{}<>/\\|+*&^%$#@=~`'\"-_"

EXACT_MATCH_BONUS = 100
PHRASE_MATCH_BONUS = 50
ALL_TOKENS_BONUS = 25
PRIMARY_WEIGHT = 15
REFERENCE_WEIGHT = 8
SUMMARY_WEIGHT = 4


def load_knowledge(path: Path | None = None) -> dict[str, Any]:
    """Doc knowledge_base.json; raise loi JSON/IO ro rang neu file hong."""

    resolved = path or KNOWLEDGE_PATH
    return json.loads(resolved.read_text(encoding="utf-8"))


def load_entries(path: Path | None = None) -> list[dict[str, Any]]:
    """Tra ve tat ca entry voi truong ``type`` duoc gan theo section."""

    knowledge = load_knowledge(path)
    entries: list[dict[str, Any]] = []
    for section, entry_type in SECTIONS:
        for raw in knowledge.get(section) or []:
            entry = dict(raw)
            entry["type"] = entry_type
            entries.append(entry)
    return entries


def _normalize(text: str) -> str:
    """casefold + bo dau tieng Viet + gop khoang trang (tuong minh, deterministic)."""

    folded = unicodedata.normalize("NFD", str(text).casefold())
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(stripped.split())


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    for char in PUNCTUATION:
        normalized = normalized.replace(char, " ")
    return {token for token in normalized.split() if token}


def _join(values: Any) -> str:
    if isinstance(values, list | tuple):
        return " ".join(str(value) for value in values)
    return str(values or "")


def _primary_text(entry: dict[str, Any]) -> str:
    material = [
        entry.get("id"),
        entry.get("name"),
        _join(entry.get("aliases")),
        _join(entry.get("tags")),
    ]
    return _normalize(" ".join(str(part or "") for part in material))


def _reference_text(entry: dict[str, Any]) -> str:
    material = [
        entry.get("category"),
        _join(entry.get("categories")),
        _join(entry.get("owasp_ids")),
        _join(entry.get("atlas_ids")),
        entry.get("url"),
    ]
    return _normalize(" ".join(str(part or "") for part in material))


def _summary_text(entry: dict[str, Any]) -> str:
    material = [_join(entry.get(field)) for field in SUMMARY_FIELDS]
    return _normalize(" ".join(material))


def _identity_values(entry: dict[str, Any]) -> set[str]:
    values = {_normalize(entry.get("id") or "")}
    values.update(_normalize(alias) for alias in entry.get("aliases") or [])
    return {value for value in values if value}


def _score(entry: dict[str, Any], query: str, tokens: set[str]) -> int:
    primary = _primary_text(entry)
    references = _reference_text(entry)
    summary = _summary_text(entry)
    score = 0

    if query and query in _identity_values(entry):
        score += EXACT_MATCH_BONUS
    if query and len(query) >= 4 and query in primary:
        score += PHRASE_MATCH_BONUS
    if tokens and all(token in primary for token in tokens):
        score += ALL_TOKENS_BONUS
    for token in tokens:
        if token in primary:
            score += PRIMARY_WEIGHT
        if token in references:
            score += REFERENCE_WEIGHT
        if token in summary:
            score += SUMMARY_WEIGHT
    return score


def search_knowledge(
    query: str,
    *,
    top_k: int = 5,
    entry_type: str | None = None,
    path: Path | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    """Tim kiem va xep hang theo diem; tie-break theo id de tai lap ket qua."""

    if entry_type is not None and entry_type not in ENTRY_TYPES:
        raise ValueError(f"entry_type must be one of {ENTRY_TYPES}, got {entry_type!r}")

    normalized_query = _normalize(query)
    tokens = _tokens(query)
    results: list[tuple[int, dict[str, Any]]] = []
    for entry in load_entries(path):
        if entry_type is not None and entry.get("type") != entry_type:
            continue
        score = _score(entry, normalized_query, tokens)
        if score > 0:
            results.append((score, entry))
    results.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    if top_k > 0:
        results = results[:top_k]
    return results


def find_by_id(entry_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    target = _normalize(entry_id)
    return [entry for entry in load_entries(path) if _normalize(entry.get("id") or "") == target]


def _links(entry: dict[str, Any]) -> str:
    values = [
        entry.get("category"),
        *(entry.get("categories") or []),
        *(entry.get("owasp_ids") or []),
        *(entry.get("atlas_ids") or []),
    ]
    return ", ".join(str(value) for value in values if value)


def format_results(results: list[tuple[int, dict[str, Any]]]) -> str:
    if not results:
        return "Khong tim thay ket qua."
    lines = [f"{'SCORE':>5}  {'ID':<26} {'TYPE':<10} {'NAME':<44} LINKS"]
    for score, entry in results:
        name = str(entry.get("name") or "")
        if len(name) > 44:
            name = name[:41] + "..."
        lines.append(
            f"{score:>5}  {str(entry.get('id') or ''):<26} "
            f"{str(entry.get('type') or ''):<10} {name:<44} {_links(entry)}"
        )
    return "\n".join(lines)


def _configure_stdout() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):  # pragma: no cover - console khong doi duoc
        pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Tim kiem kho tri thuc OWASP LLM Top 10, MITRE ATLAS va ky thuat tan cong."
    )
    parser.add_argument("query", nargs="?", help="Ten ky thuat, alias hoac ma OWASP/ATLAS.")
    parser.add_argument("--id", dest="entry_id", help="Tra cuu chinh xac theo entry id.")
    parser.add_argument("--type", choices=ENTRY_TYPES, help="Gioi han loai entry.")
    parser.add_argument("--top", type=int, default=5, help="So ket qua toi da (mac dinh 5).")
    parser.add_argument("--json", action="store_true", help="In JSON thay vi bang.")
    parser.add_argument("--kb", type=Path, help="Duong dan knowledge_base.json thay the.")
    args = parser.parse_args(argv)

    if args.entry_id:
        results = [(EXACT_MATCH_BONUS, entry) for entry in find_by_id(args.entry_id, args.kb)]
    elif args.query:
        results = search_knowledge(
            args.query, top_k=args.top, entry_type=args.type, path=args.kb
        )
    else:
        parser.error("can cung cap query hoac --id")

    if args.json:
        payload = [{"score": score, **entry} for score, entry in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_results(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
