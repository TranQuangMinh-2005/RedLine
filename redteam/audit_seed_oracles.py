#!/usr/bin/env python3
"""Audit whether every seed oracle can be evaluated by the HTTP matrix runner."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from redteam.attacks.validate_seeds import DEFAULT_LIBRARY, load_seeds
from redteam.run_seed_matrix import RUNNER_EVIDENCE_SOURCES, requested_other_customers


def inferred_checks(seed: dict[str, Any]) -> list[str]:
    material = " ".join(
        (
            str(seed.get("target_asset") or ""),
            str(seed.get("expected_success_signal") or ""),
            str(seed.get("oracle", {}).get("success_when") or ""),
        )
    ).casefold()
    checks: list[str] = []
    if "canary" in material:
        checks.append("delivered_canary")
    if any(term in material for term in ("system prompt", "system fragment", "instruction nội bộ")):
        checks.append("system_prompt_fragment")
    if requested_other_customers(seed):
        if "email" in material:
            checks.append("exact_mock_email")
        if any(term in material for term in ("phone", "điện thoại")):
            checks.append("exact_mock_phone")
        if any(term in material for term in ("address", "địa chỉ")):
            checks.append("exact_mock_address")
    return checks


def setup_supported(seed: dict[str, Any]) -> bool:
    setup = seed.get("setup") or {}
    return bool(
        (setup.get("document_id") and setup.get("rag_document"))
        or setup.get("rag_documents")
    )


def audit_seed(seed: dict[str, Any]) -> dict[str, Any]:
    required = set(seed["oracle"]["evidence_sources"])
    missing = sorted(required - RUNNER_EVIDENCE_SOURCES)
    checks = inferred_checks(seed)
    reasons: list[str] = []
    unsupported_setup = bool(seed.get("setup")) and not setup_supported(seed)
    if unsupported_setup:
        reasons.append("setup_not_executed_by_http_runner")
    if missing:
        reasons.append("missing_evidence:" + ",".join(missing))
    if not checks:
        reasons.append("no_exact_automatic_positive_check")

    if unsupported_setup:
        mode = "inconclusive_until_setup_supported"
    elif missing:
        mode = "external_evidence_required"
    elif checks:
        mode = "automatic_positive_and_refusal_negative"
    else:
        mode = "semantic_manual_review"

    return {
        "seed_id": seed["attack_id"],
        "category": seed["category"],
        "attack_type": seed["attack_type"],
        "setup_supported": setup_supported(seed),
        "evaluation_mode": mode,
        "required_evidence_sources": sorted(required),
        "runner_evidence_sources": sorted(required & RUNNER_EVIDENCE_SOURCES),
        "missing_evidence_sources": missing,
        "automatic_positive_checks": checks,
        "reasons": reasons,
    }


def build_report(library: Path) -> dict[str, Any]:
    per_seed = [audit_seed(seed) for seed in load_seeds(library)]
    modes = Counter(item["evaluation_mode"] for item in per_seed)
    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in per_seed:
        grouped[item["category"]].append(item)
    for category, items in sorted(grouped.items()):
        by_category[category] = {
            "seed_count": len(items),
            "evaluation_modes": dict(sorted(Counter(i["evaluation_mode"] for i in items).items())),
            "missing_evidence_sources": sorted(
                {source for item in items for source in item["missing_evidence_sources"]}
            ),
            "seed_ids": [item["seed_id"] for item in items],
        }
    return {
        "schema_version": "1.0",
        "library": str(library),
        "runner_evidence_sources": sorted(RUNNER_EVIDENCE_SOURCES),
        "seed_count": len(per_seed),
        "evaluation_mode_counts": dict(sorted(modes.items())),
        "categories": by_category,
        "seeds": per_seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.library)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
