"""Validate the Week 2 seed library without adding a JSON Schema dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ATTACKS_DIR = Path(__file__).resolve().parent
DEFAULT_LIBRARY = ATTACKS_DIR / "seeds" / "seed_library_v1_base.json"
DEFAULT_MUTATION_LIBRARY = ATTACKS_DIR / "seeds" / "seed_mutations_v2.json"
DEFAULT_TAXONOMY = ATTACKS_DIR / "taxonomy" / "taxonomy.yml"
OWASP_SCOPE = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"}
REQUIRED_FIELDS = {
    "schema_version", "attack_id", "parent_attack_id", "attempt_idx", "title",
    "objective", "category", "technique", "attack_type", "prompt", "turns", "setup",
    "target_asset", "expected_success_signal", "oracle", "expected_safe_behavior",
    "owasp_ids", "atlas_ids", "language", "severity", "source_refs", "evidence_refs",
    "cleanup", "status",
}
OPTIONAL_FIELDS = {
    "difficulty", "attack_chain", "preconditions", "negative_control_id", "repetitions",
    "design_notes", "safety_domain", "negative_control_prompt", "context_fixture", "transport",
}
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
VALID_ATTACK_TYPES = {"single_turn", "multi_turn", "indirect", "indirect_multi_turn"}
VALID_LANGUAGES = {"vi", "en", "mixed", "encoded"}
VALID_STATUSES = {"draft", "reviewed", "tested"}
VALID_EVIDENCE = {
    "response",
    "audit_log",
    "database",
    "retrieval_log",
    "guardrail_action",
    "latency",
    "frontend_sink",
    "spreadsheet_sink",
    "downstream_parser",
}
VALID_SAFETY_DOMAINS = {
    "abusive_language",
    "political_content",
    "out_of_scope",
    "unauthorized_commitment",
    "brand_safety",
    "cyber_safety",
    "illegal_activity",
    "violence_extremism",
    "self_harm",
    "sexual_content",
    "child_safety",
    "bias_discrimination",
    "fraud",
    "impersonation",
}
ID_RE = re.compile(r"^[A-Z]+-[A-Z]+-\d{3}$")
SECRET_RE = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,})")


def load_seeds(path: Path) -> list[dict[str, Any]]:
    """Load the canonical pretty JSON array or a legacy JSONL library."""

    content = path.read_text(encoding="utf-8")
    if content.lstrip().startswith("["):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON array: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(seed, dict) for seed in parsed):
            raise ValueError("seed library must be an array of JSON objects")
        return parsed

    seeds: list[dict[str, Any]] = []
    for line_number, raw in enumerate(content.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            seed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(seed, dict):
            raise ValueError(f"line {line_number}: seed must be a JSON object")
        seed["_line"] = line_number
        seeds.append(seed)
    return seeds


def validate_library(
    library: Path = DEFAULT_LIBRARY, taxonomy_path: Path = DEFAULT_TAXONOMY
) -> tuple[list[str], dict[str, Any]]:
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))["categories"]
    seeds = load_seeds(library)
    errors: list[str] = []
    ids: set[str] = set()
    prompt_hashes: dict[str, str] = {}
    categories: Counter[str] = Counter()
    difficulties: Counter[str] = Counter()
    owasp_seen: set[str] = set()

    for seed_number, seed in enumerate(seeds, 1):
        line = seed.pop("_line", seed_number)
        attack_id = str(seed.get("attack_id", f"line-{line}"))
        missing = REQUIRED_FIELDS - seed.keys()
        extra = seed.keys() - ALLOWED_FIELDS
        if missing:
            errors.append(f"{attack_id}: missing fields {sorted(missing)}")
        if extra:
            errors.append(f"{attack_id}: unknown fields {sorted(extra)}")
        if seed.get("schema_version") != "1.0":
            errors.append(f"{attack_id}: schema_version must be 1.0")
        if not ID_RE.fullmatch(attack_id):
            errors.append(f"{attack_id}: invalid attack_id format")
        if attack_id in ids:
            errors.append(f"{attack_id}: duplicate attack_id")
        ids.add(attack_id)
        if seed.get("parent_attack_id") is not None or seed.get("attempt_idx") != 0:
            errors.append(f"{attack_id}: base seed must have null parent and attempt_idx=0")

        category = seed.get("category")
        if category not in taxonomy:
            errors.append(f"{attack_id}: unknown category {category!r}")
        else:
            categories[category] += 1
            declared = set(taxonomy[category].get("owasp_ids", []))
            actual = set(seed.get("owasp_ids", []))
            if not actual or not actual <= declared:
                errors.append(
                    f"{attack_id}: OWASP {sorted(actual)} not allowed by "
                    f"category {sorted(declared)}"
                )
            owasp_seen.update(actual)

        attack_type = seed.get("attack_type")
        prompt = seed.get("prompt", "")
        turns = seed.get("turns", [])
        setup = seed.get("setup")
        if attack_type not in VALID_ATTACK_TYPES:
            errors.append(f"{attack_id}: invalid attack_type {attack_type!r}")
        multi_turn_types = {"multi_turn", "indirect_multi_turn"}
        indirect_types = {"indirect", "indirect_multi_turn"}
        if attack_type in multi_turn_types and len(turns) < 2:
            errors.append(f"{attack_id}: multi-turn attack requires at least two turns")
        if attack_type not in multi_turn_types and turns:
            errors.append(f"{attack_id}: this attack_type may not define turns")
        if attack_type in indirect_types:
            valid_setup = isinstance(setup, dict) and any(
                setup.get(key) for key in ("rag_document", "rag_documents", "ticket_fixture")
            )
            if not valid_setup:
                errors.append(f"{attack_id}: indirect attack requires a controlled fixture")
        elif setup is not None:
            errors.append(f"{attack_id}: only indirect seeds may define setup")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{attack_id}: prompt must be non-empty")

        normalized = " ".join(prompt.lower().split())
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        if digest in prompt_hashes:
            errors.append(f"{attack_id}: duplicate normalized prompt of {prompt_hashes[digest]}")
        prompt_hashes[digest] = attack_id
        if SECRET_RE.search(prompt) or SECRET_RE.search(json.dumps(setup or {})):
            errors.append(f"{attack_id}: possible real credential in seed")

        oracle = seed.get("oracle", {})
        if not isinstance(oracle, dict) or not oracle.get("success_when"):
            errors.append(f"{attack_id}: oracle.success_when is required")
        evidence = set(oracle.get("evidence_sources", [])) if isinstance(oracle, dict) else set()
        if not evidence or not evidence <= VALID_EVIDENCE:
            errors.append(f"{attack_id}: invalid oracle evidence_sources")
        if seed.get("language") not in VALID_LANGUAGES:
            errors.append(f"{attack_id}: invalid language")
        if seed.get("status") not in VALID_STATUSES:
            errors.append(f"{attack_id}: invalid status")
        if seed.get("transport", "native_chat") not in {"native_chat", "openai_messages"}:
            errors.append(f"{attack_id}: invalid transport")
        difficulty = seed.get("difficulty")
        if difficulty is not None:
            if difficulty not in {"L1", "L2", "L3", "L4"}:
                errors.append(f"{attack_id}: invalid difficulty")
            else:
                difficulties[difficulty] += 1
            if not seed.get("design_notes"):
                errors.append(f"{attack_id}: difficulty-tagged seed requires design_notes")
            if not seed.get("preconditions"):
                errors.append(f"{attack_id}: difficulty-tagged seed requires preconditions")
            if not seed.get("attack_chain"):
                errors.append(f"{attack_id}: difficulty-tagged seed requires attack_chain")
            if not isinstance(seed.get("repetitions"), int):
                errors.append(f"{attack_id}: difficulty-tagged seed requires repetitions")
        safety_domain = seed.get("safety_domain")
        if safety_domain is not None:
            if safety_domain not in VALID_SAFETY_DOMAINS:
                errors.append(f"{attack_id}: invalid safety_domain")
            if not seed.get("negative_control_prompt"):
                errors.append(f"{attack_id}: safety seed requires negative_control_prompt")
            context_fixture = seed.get("context_fixture")
            if not isinstance(context_fixture, dict):
                errors.append(f"{attack_id}: safety seed requires context_fixture")
            else:
                fraction = context_fixture.get("target_context_fraction")
                if not isinstance(fraction, int | float) or not 0.1 <= fraction <= 0.8:
                    errors.append(f"{attack_id}: invalid target_context_fraction")
                if context_fixture.get("payload_position") not in {"beginning", "middle", "end"}:
                    errors.append(f"{attack_id}: invalid payload_position")

    if len(seeds) < 70:
        errors.append(f"library: expected at least 70 base seeds, found {len(seeds)}")
    if len(categories) < 7:
        errors.append(f"library: expected at least 7 categories, found {len(categories)}")
    if owasp_seen != OWASP_SCOPE:
        missing_owasp = sorted(OWASP_SCOPE - owasp_seen)
        errors.append(f"library: OWASP coverage mismatch; missing={missing_owasp}")

    report = {
        "seed_count": len(seeds),
        "category_counts": dict(sorted(categories.items())),
        "difficulty_counts": dict(sorted(difficulties.items())),
        "owasp_coverage": sorted(owasp_seen),
        "valid": not errors,
    }
    return errors, report


def validate_mutation_library(
    library: Path,
    base_library: Path = DEFAULT_LIBRARY,
    taxonomy_path: Path = DEFAULT_TAXONOMY,
) -> tuple[list[str], dict[str, Any]]:
    """Validate an attack-iteration overlay without weakening base-library rules."""

    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))["categories"]
    mutations = load_seeds(library)
    base_ids = {seed["attack_id"] for seed in load_seeds(base_library)}
    errors: list[str] = []
    ids: set[str] = set()

    for index, seed in enumerate(mutations, 1):
        attack_id = str(seed.get("attack_id", f"line-{index}"))
        missing = REQUIRED_FIELDS - seed.keys()
        extra = seed.keys() - ALLOWED_FIELDS
        if missing:
            errors.append(f"{attack_id}: missing fields {sorted(missing)}")
        if extra:
            errors.append(f"{attack_id}: unknown fields {sorted(extra)}")
        if not ID_RE.fullmatch(attack_id):
            errors.append(f"{attack_id}: invalid attack_id format")
        if attack_id in ids or attack_id in base_ids:
            errors.append(f"{attack_id}: duplicate attack_id")
        ids.add(attack_id)
        parent = seed.get("parent_attack_id")
        if parent not in base_ids:
            errors.append(f"{attack_id}: parent_attack_id must reference a base seed")
        if not isinstance(seed.get("attempt_idx"), int) or seed.get("attempt_idx", 0) < 1:
            errors.append(f"{attack_id}: mutation attempt_idx must be >= 1")
        if seed.get("category") not in taxonomy:
            errors.append(f"{attack_id}: unknown category {seed.get('category')!r}")
        if seed.get("attack_type") not in VALID_ATTACK_TYPES:
            errors.append(f"{attack_id}: invalid attack_type")
        if seed.get("transport", "native_chat") not in {"native_chat", "openai_messages"}:
            errors.append(f"{attack_id}: invalid transport")
        if seed.get("transport") == "openai_messages" and not any(
            turn.get("role") == "assistant" for turn in seed.get("turns", [])
        ):
            errors.append(f"{attack_id}: openai_messages requires an assistant turn")
        if seed.get("attack_type") in {"multi_turn", "indirect_multi_turn"} and len(seed.get("turns", [])) < 2:
            errors.append(f"{attack_id}: multi-turn attack requires at least two turns")
        oracle = seed.get("oracle", {})
        evidence = set(oracle.get("evidence_sources", [])) if isinstance(oracle, dict) else set()
        if not oracle.get("success_when") or not evidence or not evidence <= VALID_EVIDENCE:
            errors.append(f"{attack_id}: invalid oracle")
        if seed.get("difficulty") not in {"L3", "L4"}:
            errors.append(f"{attack_id}: mutation must declare L3 or L4 difficulty")
        if not seed.get("attack_chain") or not seed.get("preconditions"):
            errors.append(f"{attack_id}: mutation requires attack_chain and preconditions")
        if not isinstance(seed.get("repetitions"), int) or seed.get("repetitions", 0) < 3:
            errors.append(f"{attack_id}: mutation repetitions must be >= 3")
        if not seed.get("design_notes"):
            errors.append(f"{attack_id}: mutation requires design_notes")

    return errors, {"seed_count": len(mutations), "valid": not errors, "base_seed_count": len(base_ids)}


def validate_versioned_library(
    library: Path,
    base_library: Path = DEFAULT_LIBRARY,
    mutation_library: Path = DEFAULT_MUTATION_LIBRARY,
) -> tuple[list[str], dict[str, Any]]:
    """Validate a materialized v2 library as an unchanged base plus reviewed mutations."""

    combined = load_seeds(library)
    base = load_seeds(base_library)
    mutations = load_seeds(mutation_library)
    errors, mutation_report = validate_mutation_library(mutation_library, base_library)
    if combined[: len(base)] != base:
        errors.append("library: v2 must preserve the canonical base seeds unchanged and in order")
    if combined[len(base) :] != mutations:
        errors.append("library: v2 mutation suffix does not match seed_mutations_v2.json")
    ids = [seed.get("attack_id") for seed in combined]
    if len(ids) != len(set(ids)):
        errors.append("library: v2 contains duplicate attack IDs")
    return errors, {
        "seed_count": len(combined),
        "base_seed_count": len(base),
        "mutation_seed_count": mutation_report["seed_count"],
        "valid": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", nargs="?", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--mutations", action="store_true")
    parser.add_argument("--versioned", action="store_true")
    parser.add_argument("--base-library", type=Path, default=DEFAULT_LIBRARY)
    args = parser.parse_args()
    if args.versioned:
        errors, report = validate_versioned_library(args.library, args.base_library)
    elif args.mutations:
        errors, report = validate_mutation_library(args.library, args.base_library)
    else:
        errors, report = validate_library(args.library)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
