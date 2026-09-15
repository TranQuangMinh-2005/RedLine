# RAG corpus runbook

## Nguồn được ingest

Corpus được duyệt nằm trong `data/rag/documents/`; mỗi file Markdown là một tài liệu public và có
front matter với tối thiểu `doc_id`, `title`, `category`, và `language`.
Nguồn mock, URL tham khảo công khai, ngày truy cập, hash SHA-256, category chuẩn hóa,
visibility và thời điểm ingest được ghi ở `data/rag/documents/manifest.jsonl`.
Nội dung được biên soạn lại cho sandbox RedShop, không sao chép nguyên văn và không
được hiểu là chính sách chính thức của nguồn tham khảo.

## Ingest

Từ thư mục repository, chạy:

```powershell
python scripts/ingest_rag.py
```

Lệnh tạo `data/rag/documents/manifest.jsonl` (một dòng một document) và
`data/rag/documents/index.json` (các chunk dùng để retrieval). Hai file là artifacts cục
bộ bị Git ignore; hash trong manifest xác định chính xác corpus của một run.

## Retrieval contract

`retrieve(query, top_k=3)` trả về chunk được xếp hạng cùng `document_id`,
`source_file`, `category`, `content_hash` và `score`. Nếu không có từ khóa giao
nhau với corpus, nó trả `[]`; caller phải thông báo là chưa xác minh được thay
vì bịa câu trả lời.

## Tách corpus kiểm thử

Tài liệu dùng để thử indirect prompt injection phải đặt trong collection/thư
mục test riêng ở giai đoạn red-team. Không đưa chúng vào `data/rag/documents/` normal
corpus.
