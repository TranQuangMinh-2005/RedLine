from __future__ import annotations

import json
from pathlib import Path

import yaml

from redteam.attacks import knowledge
from redteam.attacks.knowledge import search as search_module

REPO_ROOT = Path(__file__).resolve().parents[1]
ATTACKS_DIR = REPO_ROOT / "redteam" / "attacks"
V3CORE_LIBRARIES = (
    ATTACKS_DIR / "seeds" / "seed_library_v3core_base.json",
    ATTACKS_DIR / "seeds" / "seed_mutations_v3core.json",
)
OWASP_SCOPE = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"}


def test_search_prompt_injection_returns_owasp_atlas_and_technique() -> None:
    results = knowledge.search_knowledge("prompt injection", top_k=10)

    ids = [entry["id"] for _, entry in results]

    assert "LLM01" in ids
    assert "AML.T0051" in ids
    assert "TECH-RAG-INDIRECT" in ids


def test_search_jailbreak_returns_roleplay_technique() -> None:
    results = knowledge.search_knowledge("jailbreak")

    ids = [entry["id"] for _, entry in results]

    assert "AML.T0054" in ids
    assert "TECH-ROLEPLAY" in ids


def test_search_accepts_unaccented_vietnamese_query() -> None:
    accented = knowledge.search_knowledge("tiêm nhiễm prompt")
    unaccented = knowledge.search_knowledge("tiem nhiem prompt")

    assert accented
    assert [entry["id"] for _, entry in accented] == [entry["id"] for _, entry in unaccented]


def test_normalize_strips_diacritics() -> None:
    assert search_module._normalize("Tấn công") == "tan cong"


def test_search_finds_technique_by_exact_id() -> None:
    results = knowledge.search_knowledge("TECH-RIP")

    assert results
    assert results[0][1]["id"] == "TECH-RIP"

    exact = knowledge.find_by_id("tech-rip")
    assert [entry["id"] for entry in exact] == ["TECH-RIP"]


def test_knowledge_base_matches_taxonomy_and_seed_library() -> None:
    knowledge_data = knowledge.load_knowledge()
    taxonomy = yaml.safe_load((ATTACKS_DIR / "taxonomy" / "taxonomy.yml").read_text("utf-8"))
    taxonomy_categories = set(taxonomy["categories"])

    seed_ids: set[str] = set()
    for library in V3CORE_LIBRARIES:
        for seed in json.loads(library.read_text(encoding="utf-8")):
            seed_ids.add(seed["attack_id"])

    techniques = knowledge_data["techniques"]
    assert 10 <= len(techniques) <= 20
    assert {technique["category"] for technique in techniques} == taxonomy_categories

    covered_owasp: set[str] = set()
    for technique in techniques:
        assert technique["id"].startswith("TECH-")
        assert set(technique["owasp_ids"]) <= OWASP_SCOPE
        assert set(technique["atlas_ids"]) <= {
            entry["id"] for entry in knowledge_data["atlas"]
        }
        assert set(technique["seed_refs"]) <= seed_ids
        covered_owasp.update(technique["owasp_ids"])

    assert covered_owasp == OWASP_SCOPE


def test_taxonomy_atlas_ids_are_documented() -> None:
    knowledge_data = knowledge.load_knowledge()
    taxonomy = yaml.safe_load((ATTACKS_DIR / "taxonomy" / "taxonomy.yml").read_text("utf-8"))

    used_atlas: set[str] = set()
    for category in taxonomy["categories"].values():
        used_atlas.update(category["atlas_ids"])

    documented_atlas = {entry["id"] for entry in knowledge_data["atlas"]}

    assert used_atlas
    assert used_atlas <= documented_atlas


def test_cli_prints_table(capsys) -> None:
    exit_code = search_module.main(["prompt injection", "--top", "3"])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "SCORE" in output
    assert "LLM01" in output


def test_cli_json_output(capsys) -> None:
    exit_code = search_module.main(["jailbreak", "--json", "--top", "3"])

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert "AML.T0054" in [entry["id"] for entry in payload]
