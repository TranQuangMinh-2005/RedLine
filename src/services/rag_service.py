"""Deterministic local RAG ingestion and retrieval for the sandbox target.

Source documents remain human-readable Markdown in ``data/rag/documents``. Ingestion
creates a document-level provenance manifest and a local JSON chunk index. This
dependency-free lexical retriever is deliberately deterministic so ingestion and
tests do not depend on a remote embedding model; a vector-store adapter can
replace retrieval later without changing source provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings


CORPUS_DIR = Path("data/rag/documents")
MANIFEST_NAME = "manifest.jsonl"
INDEX_NAME = "index.json"

_CATEGORY_MAP = {
    "privacy_security": "bao_mat",
    "returns_refunds": "doi_tra_hoan_tien",
    "shipping": "van_chuyen",
    "guide_voucher": "voucher",
    "guide_ordering": "shopeefood",
    "guide_account_link": "shopeefood",
    "guide_spaylater": "thanh_toan",
    "guide_bank_account": "thanh_toan",
    "faq": "faq",
}
_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ỹ0-9]+", re.UNICODE)


@dataclass(frozen=True)
class DocumentManifest:
    document_id: str
    source_file: str
    category: str
    visibility: str
    content_hash: str
    ingested_at: str
    chunk_count: int
    title: str = ""
    language: str = "vi"
    source_note: str = ""
    reference_url: str = ""
    accessed_at: str = ""


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Parse the small YAML subset used by corpus Markdown files."""
    raw = raw.replace("\r\n", "\n")
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---", 4)
    if end == -1:
        return {}, raw
    metadata: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, raw[end + 4 :].lstrip("\r\n")


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            boundary = max(cleaned.rfind("\n", start, end), cleaned.rfind(" ", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _token_counts(text: str) -> Counter[str]:
    return Counter(token.casefold() for token in _TOKEN_RE.findall(text))


def _iter_source_files(corpus_dir: Path) -> list[Path]:
    return sorted(corpus_dir.glob("*.md"))


def ingest_corpus(
    corpus_dir: Path | str = CORPUS_DIR,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    ingested_at: str | None = None,
) -> list[DocumentManifest]:
    """Build provenance manifest and chunk index from approved Markdown files."""
    settings = get_settings()
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.RAG_CHUNK_OVERLAP
    ingested_at = ingested_at or datetime.now(UTC).isoformat()
    manifests: list[DocumentManifest] = []
    chunks: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for path in _iter_source_files(corpus_dir):
        raw_bytes = path.read_bytes()
        metadata, content = _parse_front_matter(raw_bytes.decode("utf-8"))
        required = {"doc_id", "title", "category", "language"}
        missing = sorted(required.difference(metadata))
        if missing:
            raise ValueError(f"missing required metadata in {path.name}: {', '.join(missing)}")
        document_id = metadata["doc_id"]
        if document_id in used_ids:
            raise ValueError(f"duplicate document_id: {document_id}")
        used_ids.add(document_id)
        source_chunks = _chunk_text(content, chunk_size=chunk_size, overlap=chunk_overlap)
        category_raw = metadata["category"]
        manifest = DocumentManifest(
            document_id=document_id,
            source_file=path.name,
            category=_CATEGORY_MAP.get(category_raw, category_raw),
            visibility="public",
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
            ingested_at=ingested_at,
            chunk_count=len(source_chunks),
            title=metadata["title"],
            language=metadata["language"],
            source_note=metadata.get("source_note", ""),
            reference_url=metadata.get("reference_url", ""),
            accessed_at=metadata.get("accessed_at", ""),
        )
        manifests.append(manifest)
        for chunk_index, chunk_text in enumerate(source_chunks):
            chunks.append({
                **asdict(manifest),
                "chunk_id": f"{document_id}:{chunk_index}",
                "chunk_index": chunk_index,
                "text": chunk_text,
            })
    (corpus_dir / MANIFEST_NAME).write_text(
        "".join(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n" for item in manifests),
        encoding="utf-8",
    )
    (corpus_dir / INDEX_NAME).write_text(
        json.dumps(
            {
                "version": 1,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "chunks": chunks,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifests


def retrieve(query: str, *, top_k: int = 3, corpus_dir: Path | str = CORPUS_DIR) -> list[dict[str, Any]]:
    """Return relevant chunks with document ID and source provenance."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    index_path = Path(corpus_dir) / INDEX_NAME
    if not index_path.exists():
        raise RuntimeError("RAG index is missing; run ingest_corpus first")
    query_terms = _token_counts(query)
    if not query_terms:
        return []
    raw_index = json.loads(index_path.read_text(encoding="utf-8"))
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in raw_index.get("chunks", []):
        chunk_terms = _token_counts(chunk["text"])
        score = sum(min(count, chunk_terms[token]) for token, count in query_terms.items())
        if score:
            scored.append((float(score), chunk))
    scored.sort(key=lambda item: (-item[0], item[1]["document_id"], item[1]["chunk_index"]))
    return [{**chunk, "score": score} for score, chunk in scored[:top_k]]


def add_document(
    *,
    doc_id: str,
    title: str,
    content: str,
    category: str = "faq",
    language: str = "vi",
    source_note: str = "",
    corpus_dir: Path | str = CORPUS_DIR,
) -> DocumentManifest:
    """Thêm (hoặc thay) một tài liệu Markdown vào corpus rồi re-ingest.

    Có hiệu lực ngay cho retrieval vì ingest ghi đè index.json mà
    retrieve() đọc lại mỗi request (không cache).

    Raises:
        ValueError: nếu doc_id/title rỗng hoặc doc_id chứa ký tự không an toàn.
    """
    doc_id = (doc_id or "").strip()
    title = (title or "").strip()
    if not doc_id:
        raise ValueError("doc_id is required")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", doc_id):
        raise ValueError("doc_id chỉ được chứa chữ, số, dấu gạch ngang, gạch dưới và dấu chấm")
    if not title:
        raise ValueError("title is required")
    if content is None:
        raise ValueError("content is required")

    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # Front matter nhỏ gọn + nội dung thô
    front = f"---\ndoc_id: {doc_id}\ntitle: \"{title}\"\ncategory: {category}\nlanguage: {language}\n"
    if source_note:
        front += f"source_note: \"{source_note}\"\n"
    front += "---\n\n"
    path = corpus_dir / f"{doc_id}.md"
    path.write_text(front + content.lstrip("\n"), encoding="utf-8")

    # Re-ingest toàn bộ corpus (sinh manifest + index mới)
    manifests = ingest_corpus(corpus_dir)
    for manifest in manifests:
        if manifest.document_id == doc_id:
            return manifest
    raise RuntimeError(f"document {doc_id} was not present after re-ingest")


def remove_document(doc_id: str, *, corpus_dir: Path | str = CORPUS_DIR) -> bool:
    """Xoá tài liệu khỏi corpus (nếu tồn tại) rồi re-ingest.

    Returns:
        True nếu file đã bị xoá, False nếu không có tài liệu nào như vậy.
    """
    doc_id = (doc_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", doc_id):
        raise ValueError("doc_id chỉ được chứa chữ, số, dấu gạch ngang, gạch dưới và dấu chấm")

    corpus_dir = Path(corpus_dir)
    path = corpus_dir / f"{doc_id}.md"
    if not path.exists():
        return False
    path.unlink()
    ingest_corpus(corpus_dir)
    return True


def list_documents(*, corpus_dir: Path | str = CORPUS_DIR) -> list[DocumentManifest]:
    """Danh sách tài liệu đã ingest (đọc từ manifest.jsonl)."""
    corpus_dir = Path(corpus_dir)
    manifest_path = corpus_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return []
    manifests: list[DocumentManifest] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            manifests.append(DocumentManifest(**json.loads(line)))
    return manifests
