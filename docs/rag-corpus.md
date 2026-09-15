# RAG corpus runbook

## Nguồn được ingest

Corpus được duyệt nằm trong `data/rag/documents/`; mỗi file Markdown là một tài liệu public và có
front matter với tối thiểu `doc_id`, `title`, `category`, và `language`.
Nguồn, URL tham khảo công khai, ngày truy cập, hash SHA-256, category chuẩn hóa,
visibility và thời điểm ingest được ghi ở `data/rag/documents/manifest.jsonl`.

Corpus hiện tại gồm **8 tài liệu công khai của ShopeeFood** (chính sách bảo mật, vận chuyển,
trả hàng/hoàn tiền và tin tức) lấy từ `help.shopee.vn`, được chuẩn hoá thành Markdown
(`data/shopee-rag/standardized/`). Mỗi file giữ nguyên front matter gốc gồm
`source_url`, `retrieved_at`, `document_version`, `customer_role` để minh bạch nguồn.
Đây là tài liệu công khai tham khảo — **không phải** dữ liệu khách hàng; mọi dữ liệu
khách hàng/đơn hàng/ticket trong target đều là mock riêng (xem `docs/asset-inventory.md`).

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
