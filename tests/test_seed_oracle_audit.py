from __future__ import annotations

from redteam.attacks.validate_seeds import DEFAULT_LIBRARY
from redteam.audit_seed_oracles import build_report


def test_oracle_audit_covers_every_seed_and_category() -> None:
    report = build_report(DEFAULT_LIBRARY)

    assert report["seed_count"] == 121
    assert sum(item["seed_count"] for item in report["categories"].values()) == 121
    assert {item["seed_id"] for item in report["seeds"]}
    assert len({item["seed_id"] for item in report["seeds"]}) == 121


def test_indirect_seeds_report_setup_support_accurately() -> None:
    report = build_report(DEFAULT_LIBRARY)
    indirect = [item for item in report["seeds"] if item["attack_type"].startswith("indirect")]

    assert indirect
    supported = [item for item in indirect if item["setup_supported"]]
    unsupported = [item for item in indirect if not item["setup_supported"]]
    assert len(supported) == 12
    assert {item["seed_id"] for item in unsupported} == {"ADV-TOOL-001", "RIP-TOL-001"}
    assert all(
        item["evaluation_mode"] == "inconclusive_until_setup_supported"
        for item in unsupported
    )


def test_improper_output_oracles_require_downstream_evidence() -> None:
    report = build_report(DEFAULT_LIBRARY)
    improper = [item for item in report["seeds"] if item["category"] == "improper_output"]

    assert len(improper) == 5
    assert all(item["missing_evidence_sources"] for item in improper)
