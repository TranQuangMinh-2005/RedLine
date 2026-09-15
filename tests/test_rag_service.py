from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.services.rag_service import CORPUS_DIR, INDEX_NAME, MANIFEST_NAME, ingest_corpus, retrieve


def _write_document(path: Path, *, doc_id: str, category: str, body: str) -> None:
    path.write_text(
        f"---\ndoc_id: {doc_id}\ntitle: Test\ncategory: {category}\nlanguage: vi\n---\n# Test\n\n{body}\n",
        encoding="utf-8",
    )


def test_ingestion_writes_manifest_and_chunk_provenance(tmp_path: Path) -> None:
    _write_document(tmp_path / "returns.md", doc_id="returns-policy", category="returns_refunds", body="Điều kiện hoàn tiền áp dụng khi đơn hợp lệ.")
    manifests = ingest_corpus(tmp_path, chunk_size=80, chunk_overlap=10, ingested_at="2026-09-15T00:00:00+00:00")
    assert manifests[0].category == "doi_tra_hoan_tien"
    assert manifests[0].visibility == "public"
    assert len(manifests[0].content_hash) == 64
    assert (tmp_path / MANIFEST_NAME).exists()
    index = json.loads((tmp_path / INDEX_NAME).read_text(encoding="utf-8"))
    assert index["chunks"][0]["document_id"] == "returns-policy"
    assert index["chunks"][0]["source_file"] == "returns.md"


def test_retrieve_returns_source_and_document_id(tmp_path: Path) -> None:
    _write_document(tmp_path / "shipping.md", doc_id="shipping-policy", category="shipping", body="Nếu đơn giao chậm, hãy kiểm tra trạng thái giao hàng và mã đơn.")
    _write_document(tmp_path / "voucher.md", doc_id="voucher-guide", category="guide_voucher", body="E-Voucher xuất hiện trong thông báo khuyến mãi sau khi thanh toán.")
    ingest_corpus(tmp_path, chunk_size=200, chunk_overlap=20, ingested_at="2026-09-15T00:00:00+00:00")
    results = retrieve("đơn giao chậm", corpus_dir=tmp_path)
    assert results[0]["document_id"] == "shipping-policy"
    assert results[0]["source_file"] == "shipping.md"
    assert results[0]["score"] > 0


def test_retrieve_returns_empty_when_knowledge_base_cannot_verify(tmp_path: Path) -> None:
    _write_document(tmp_path / "voucher.md", doc_id="voucher-guide", category="guide_voucher", body="E-Voucher xuất hiện trong thông báo khuyến mãi.")
    ingest_corpus(tmp_path, chunk_size=200, chunk_overlap=20, ingested_at="2026-09-15T00:00:00+00:00")
    assert retrieve("điều trị thú cưng", corpus_dir=tmp_path) == []


def test_retrieve_handles_an_ambiguous_query_with_ranked_sources(tmp_path: Path) -> None:
    _write_document(tmp_path / "shipping.md", doc_id="shipping-policy", category="shipping", body="Trạng thái đơn giao hàng được cập nhật trong mục Đơn mua.")
    _write_document(tmp_path / "returns.md", doc_id="returns-policy", category="returns_refunds", body="Yêu cầu hoàn tiền cần cung cấp mã đơn hàng hợp lệ.")
    ingest_corpus(tmp_path, chunk_size=200, chunk_overlap=20, ingested_at="2026-09-15T00:00:00+00:00")

    results = retrieve("trạng thái đơn hàng", top_k=2, corpus_dir=tmp_path)

    assert len(results) == 2
    assert results[0]["document_id"] == "shipping-policy"
    assert results[0]["score"] >= results[1]["score"]


def test_ingestion_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    _write_document(tmp_path / "one.md", doc_id="duplicate", category="faq", body="Ná»™i dung má»™t.")
    _write_document(tmp_path / "two.md", doc_id="duplicate", category="faq", body="Ná»™i dung hai.")

    with pytest.raises(ValueError, match="duplicate document_id"):
        ingest_corpus(tmp_path)


def test_ingestion_is_deterministic_except_for_timestamp(tmp_path: Path) -> None:
    _write_document(
        tmp_path / "warranty.md",
        doc_id="warranty-policy",
        category="faq",
        body="Báº£o hÃ nh sáº£n pháº©m trong mÆ°á»i hai thÃ¡ng.",
    )

    first = ingest_corpus(
        tmp_path,
        chunk_size=60,
        chunk_overlap=10,
        ingested_at="2026-09-15T00:00:00+00:00",
    )
    first_index = (tmp_path / INDEX_NAME).read_text(encoding="utf-8")
    second = ingest_corpus(
        tmp_path,
        chunk_size=60,
        chunk_overlap=10,
        ingested_at="2026-09-15T00:00:00+00:00",
    )
    second_index = (tmp_path / INDEX_NAME).read_text(encoding="utf-8")

    assert first == second
    assert first_index == second_index


def test_retrieve_honors_top_k_and_validates_it(tmp_path: Path) -> None:
    for index in range(3):
        _write_document(
            tmp_path / f"shipping-{index}.md",
            doc_id=f"shipping-{index}",
            category="shipping",
            body=f"Giao hÃ ng nhanh cho Ä‘Æ¡n hÃ ng sá»‘ {index}.",
        )
    ingest_corpus(tmp_path)

    assert len(retrieve("giao hÃ ng", top_k=2, corpus_dir=tmp_path)) == 2
    with pytest.raises(ValueError, match="top_k"):
        retrieve("giao hÃ ng", top_k=0, corpus_dir=tmp_path)


def test_retrieve_requires_an_ingested_index(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="index is missing"):
        retrieve("giao hÃ ng", corpus_dir=tmp_path)


def test_versioned_corpus_has_minimum_coverage_and_provenance(tmp_path: Path) -> None:
    source_files = sorted(Path(CORPUS_DIR).glob("*.md"))
    # Corpus hiện tại: 8 tài liệu công khai ShopeeFood (chính sách + tin tức),
    # nguồn gốc đầy đủ tại data/shopee-rag/. Ngưỡng 8 = số file corpus đang có.
    assert len(source_files) >= 8
    for source in source_files:
        shutil.copy2(source, tmp_path / source.name)

    manifests = ingest_corpus(
        tmp_path,
        ingested_at="2026-09-15T00:00:00+00:00",
    )

    assert len({item.document_id for item in manifests}) == len(manifests)
    # ShopeeFood corpus: vận chuyển (shipping), bảo mật (privacy_security),
    # trả hàng/hoàn tiền (returns_refunds) là 3 nhóm chính sách cốt lõi.
    assert {"van_chuyen", "bao_mat"}.issubset({item.category for item in manifests})
    assert "doi_tra_hoan_tien" in {item.category for item in manifests}
    assert all(item.title for item in manifests)
    assert all(item.language == "vi" for item in manifests)
    assert all(item.chunk_count > 0 for item in manifests)
