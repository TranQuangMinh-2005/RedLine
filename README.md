# RedLine — Customer Assistant Target

RedLine là môi trường sandbox dùng để kiểm thử an toàn một Customer Support Agent.
Target là **một LLM agent duy nhất** có hội thoại nhiều lượt, RAG, dữ liệu giao dịch
giả lập và các tool đọc/ghi trong sandbox.

> Chỉ sử dụng dữ liệu mock. Không kết nối dữ liệu khách hàng hoặc hệ thống vận hành thật.

## Thành phần

- FastAPI: `GET /health`, `POST /chat`.
- In-memory session store: giữ lịch sử theo `session_id`, mất khi target restart.
- Groq/OpenAI-compatible LLM: cấu hình qua biến môi trường.
- Local deterministic RAG: tài liệu Markdown, manifest provenance và JSON index.
- PostgreSQL khi chạy Docker: customer, order và ticket mock.
- Allowlisted tools: `get_customer_info`, `get_ticket`, `search_knowledge`, `create_ticket`.
- JSON audit log: request, retrieval, tool call, LLM và response; secret/PII được redact.

## Yêu cầu

- Docker Engine và Docker Compose v2; hoặc
- Python 3.11 nếu chạy/test trực tiếp trên máy.
- Groq API key hợp lệ nếu muốn gọi LLM thật.

## 1. Cấu hình

Tạo file `.env` từ mẫu:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Sửa tối thiểu hai giá trị trong `.env`:

```dotenv
LLM_API_KEY=gsk-your-key
CANARY_TOKEN=CANARY-choose-a-private-test-value
```

Không commit `.env`, API key hoặc canary đang sử dụng. `DEFENSE_PROFILE=none` là
baseline có chủ đích yếu; `basic` và `strict` dùng cho phép so sánh defense sau này.

## 2. Chạy bằng Docker

```bash
docker compose up -d --build
docker compose ps
```

Target chỉ khởi động sau khi PostgreSQL healthy. Startup của target tự động:

1. tạo database schema;
2. seed customer/order/ticket mock theo cách idempotent;
3. ingest corpus trong `data/rag/documents/`;
4. chạy FastAPI tại `http://localhost:8000`.

Kiểm tra health:

```bash
curl http://localhost:8000/health
```

Xem log:

```bash
docker compose logs -f target
```

Dừng hệ thống:

```bash
docker compose down
```

Muốn xóa cả PostgreSQL volume mock và tạo lại từ đầu:

```bash
docker compose down -v
```

Lệnh cuối xóa dữ liệu sandbox trong Docker volume; không dùng khi cần giữ evidence.

## 3. Gọi Chat API

### Turn đầu tiên

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Chính sách đổi trả như thế nào?"}'
```

Response trả một `session_id`. Dùng đúng ID đó cho turn tiếp theo:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SESSION_ID_FROM_FIRST_RESPONSE","message":"Nếu hàng bị lỗi thì sao?"}'
```

Không gửi `model` trong request. Model được khóa bằng cấu hình target để benchmark có
thể tái lập. Session nằm trong RAM, có giới hạn độ dài và không tồn tại sau khi target
restart.

## 4. Dữ liệu mock

Seed hiện cung cấp nhiều customer, order và ticket giả lập với các trạng thái khác nhau.
Các ID ổn định như `CUS-001`, `ORD-001` và `TKT-001` có thể dùng trong test.

Kiểm tra số ticket trong PostgreSQL:

```bash
docker compose exec db psql -U redline -d redline -c "SELECT count(*) FROM tickets;"
```

Sau khi yêu cầu agent tạo ticket, chạy lại câu lệnh trên hoặc query ticket ID được trả
về để xác minh side effect thực sự xảy ra trong sandbox.

## 5. RAG corpus và ingestion

Tài liệu nguồn được duyệt nằm trong `data/rag/documents/`. Mỗi file Markdown phải có
front matter với tối thiểu:

```yaml
---
doc_id: unique-document-id
title: Tiêu đề
category: faq
language: vi
source_url: mock://redshop/example
---
```

Các tài liệu tham khảo chính sách công khai được viết lại thành policy mock, kèm URL
tham khảo và ngày truy cập; không coi nội dung đó là chính sách chính thức của RedShop.

Để thêm tài liệu:

1. tạo file `.md` mới trong `data/rag/documents/`;
2. bảo đảm `doc_id` không trùng;
3. chạy ingestion;
4. thử `search_knowledge` hoặc gọi `/chat` với câu hỏi liên quan.

Chạy ingestion trong container:

```bash
docker compose exec target python scripts/ingest_rag.py
```

Chạy trực tiếp:

```bash
python scripts/ingest_rag.py
```

`manifest.jsonl` và `index.json` là artifact được tạo lại, không commit vào Git. Kết quả
retrieval bao gồm document ID, source file, content hash và score để lưu provenance.

## 6. Chạy test

Cài môi trường Python cục bộ:

```bash
python -m venv .venv
```

Kích hoạt trên PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest tests -q
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests -q
```

Các test agent/API dùng mock LLM và không được tiêu tốn quota hoặc cần kết nối mạng.

## 7. Audit log

Mỗi request có `request_id` để ghép chuỗi sự kiện:

```text
request_received → session_loaded → llm_completed
                 → retrieval_started/retrieval_completed
                 → tool_called/tool_completed
                 → response_sent
```

Log không được chứa API key, canary, system prompt nguyên văn hoặc PII chưa redact.
Với retrieval, log chỉ cần document ID và số kết quả; với side effect, log ticket ID và
trạng thái thay vì toàn bộ bản ghi.

## 8. Giới hạn hiện tại

- Đây là target red-team trong sandbox, không phải cấu hình production.
- Session chỉ nằm trong RAM và chưa phải cơ chế xác thực/phân quyền.
- Toàn bộ customer/order/ticket là dữ liệu giả lập.
- RAG là lexical retriever deterministic, chưa phải semantic vector search.
- `create_ticket` chỉ ghi Customer DB mock; agent không thể thanh toán, hoàn tiền, hủy
  đơn, gửi email/SMS hoặc gọi hệ thống thật.
- Corpus thử indirect prompt injection phải nằm ngoài corpus bình thường.

Các đặc tả liên quan nằm trong `docs/target-spec.md`, `docs/architecture.md`,
`docs/asset-inventory.md` và `docs/rag-corpus.md`.
