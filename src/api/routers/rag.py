"""RAG document management endpoints (thêm/xoá/liệt kê tài liệu trong corpus).

⚠️ ATTACK SURFACE (ghi nhận cho Day 3 recon):
- POST /rag/documents cho phép bất kỳ ai nạp nội dung vào corpus → đây CHÍNH là
  vector indirect prompt injection (LLM01) nếu không có kiểm soát truy cập.
- DELETE /rag/documents/{doc_id} cho phép xoá tài liệu → nếu bị lạm dụng sẽ làm
  hỏng corpus / tấn công khả dụng (availability).
- Không có xác thực (sandbox demo) — phải ghi rõ trong attack surface map.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.logging_config import audit_event
from src.services import rag_service

router = APIRouter(prefix="/rag", tags=["rag-documents"])


class DocumentCreateRequest(BaseModel):
    doc_id: str = Field(min_length=1, max_length=80, description="Slug duy nhất, chỉ chữ/số/-/_/.")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000, description="Nội dung đầy đủ của tài liệu")
    category: str = Field(default="faq", max_length=50)
    language: str = Field(default="vi", max_length=10)
    source_note: str = Field(default="", max_length=300)


class DocumentListEntry(BaseModel):
    document_id: str
    title: str
    category: str
    language: str
    chunk_count: int
    content_hash: str


@router.get("/documents")
def list_rag_documents() -> dict:
    """Liệt kê tài liệu đang có trong corpus (metadata, không kèm nội dung)."""
    manifests = rag_service.list_documents()
    return {
        "documents": [
            {
                "document_id": m.document_id,
                "title": m.title,
                "category": m.category,
                "language": m.language,
                "chunk_count": m.chunk_count,
                "content_hash": m.content_hash,
                "source_file": m.source_file,
            }
            for m in manifests
        ],
        "count": len(manifests),
    }


@router.post("/documents", status_code=201)
def create_rag_document(req: DocumentCreateRequest) -> dict:
    """Thêm (hoặc thay) một tài liệu vào corpus và re-ingest ngay.

    Có hiệu lực ngay cho retrieval — không cần restart container.
    """
    request_id = str(uuid4())
    try:
        manifest = rag_service.add_document(
            doc_id=req.doc_id,
            title=req.title,
            content=req.content,
            category=req.category,
            language=req.language,
            source_note=req.source_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit_event(
        "rag_document_created",
        request_id=request_id,
        doc_id=req.doc_id,
        chunk_count=manifest.chunk_count,
    )
    return {
        "status": "created",
        "document_id": manifest.document_id,
        "title": manifest.title,
        "category": manifest.category,
        "chunk_count": manifest.chunk_count,
        "content_hash": manifest.content_hash,
    }


@router.delete("/documents/{doc_id}")
def delete_rag_document(doc_id: str) -> dict:
    """Xoá tài liệu khỏi corpus và re-ingest ngay."""
    request_id = str(uuid4())
    try:
        removed = rag_service.remove_document(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail=f"document {doc_id!r} not found")

    audit_event("rag_document_deleted", request_id=request_id, doc_id=doc_id)
    return {"status": "deleted", "document_id": doc_id}