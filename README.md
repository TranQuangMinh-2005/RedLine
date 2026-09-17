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

Benchmark dùng một actor mock cố định `SCENARIO_CUSTOMER_ID=CUS-001` ở cả ba mode.
Danh tính scenario không đổi khi chuyển profile; chỉ mức phòng thủ thay đổi:

- `none`: baseline yếu, không filter và không enforce quyền tool;
- `basic`: input filter, prompt hardening và canary check;
- `strict`: thêm output filter và kiểm tra quyền tool theo actor `CUS-001`.

Các giới hạn RoE (request/phút, tổng token, số vòng tool) luôn bật, vì đây là kiểm
soát vận hành của sandbox chứ không phải defense dùng để làm tăng/giảm ASR.

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

## 3. Chạy trên Kaggle — Ollama + giao diện chat

Mở hoặc upload [`notebooks/kaggle_redline.ipynb`](notebooks/kaggle_redline.ipynb)
lên Kaggle. Notebook dùng chung launcher [`scripts/kaggle_redline.py`](scripts/kaggle_redline.py),
không chứa bản sao code khởi động.

1. Bật **Internet** và chọn **GPU T4 x2** (hoặc NVIDIA GPU đủ VRAM).
2. Tạo và Attach Kaggle Secret **`NGROK_AUTH_TOKEN`**. Có thể thêm **`CANARY_TOKEN`**
   riêng để tái lập benchmark; nếu thiếu, launcher sinh canary mới và không in ra log.
3. Trong cell cấu hình, chọn `MODEL`, `DEFENSE_PROFILE`, `ENABLE_UI`.
   Mặc định: `qwen2.5:14b`, profile `none`, UI bật. Có thể chọn `qwen2.5:7b`
   nếu cần giảm bộ nhớ/dung lượng tải.
4. Chạy cell lấy repo, cài Python và cài Ollama/Node. Python 3.11 chạy trong `.venv`
   riêng với dependency từ `uv.lock`; không cài project bằng `pip install -e .`.
5. Chạy cell khởi động. Notebook chờ tải model, seed SQLite, ingest corpus,
   kiểm thử hai chế độ và xác minh Agent thực sự gọi `search_knowledge`.
6. Khi `state=ready`, mở **Giao diện** để chat và chọn **Agent / LLM thuần** ở bên trái.
   Cell kết thúc, dịch vụ tiếp tục chạy nền. Dùng cell cuối để dừng.

| Cấu hình | Giao diện | API base | OpenAI base URL |
|---|---|---|---|
| `ENABLE_UI=True` | `https://<tunnel>` | `https://<tunnel>/api` | `https://<tunnel>/api/v1` |
| `ENABLE_UI=False` | Không chạy | `https://<tunnel>` | `https://<tunnel>/v1` |

Khi gọi từ bên ngoài, thêm header `ngrok-skip-browser-warning: true` nếu cần.
Ví dụ với UI bật:

```bash
curl -X POST https://<tunnel>/api/chat \
  -H 'Content-Type: application/json' \
  -H 'ngrok-skip-browser-warning: true' \
  -d '{"message":"Giúp tôi soạn yêu cầu hỗ trợ", "mode":"llm"}'
```

API quản lý tài liệu ở `<API base>/rag/documents`. Corpus hiện có 8 file Markdown;
launcher in số tài liệu thực tế khi ingest. Chỉ Agent sử dụng RAG.

Để chạy launcher trực tiếp trên máy Linux đã cài Ollama, GPU và dependencies:

```bash
uv sync --locked --no-dev --python 3.11
# Đặt NGROK_AUTHTOKEN trong môi trường; không đưa token vào command/log được chia sẻ.
uv run --locked --no-dev python scripts/kaggle_redline.py --ui --model qwen2.5:14b
```

UI cần Node.js/npm; notebook tự cài Node 22 nếu thiếu phiên bản phù hợp.
Bỏ `--ui` để chỉ chạy backend. Launcher hỗ trợ `--help`.

Runtime artifacts nằm trong `runs/kaggle/` (Git ignore): log, SQLite, trạng thái và
model cache nếu launcher tự khởi động Ollama. Không sửa `.env` của repo.
Launcher chỉ dừng các process do nó tạo; nếu reuse Ollama có sẵn, daemon đó vẫn chạy
và giữ cấu hình/cache cũ. Ollama tự chọn GPU phù hợp, không bảo đảm luôn dùng cả hai T4.

Notebook phục vụ phiên sandbox tương tác, không phải hosting liên tục. API quản lý
RAG/guardrail chưa có xác thực: chỉ chia sẻ tunnel với người tham gia thử nghiệm.
Dùng **Stop session** khi xong để kết thúc phiên GPU. Không công khai notebook output
hoặc artifact chứa dữ liệu thử nhạy cảm.

## 3b. Chọn endpoint & model trên web, host model trên Kaggle

Ở thanh bên trái, mục **Model → Đổi** mở panel chọn endpoint:

| Endpoint | Nguồn | Ghi chú |
|---|---|---|
| **Groq** | `api.groq.com`, key từ `GROQ_API_KEY`/`LLM_API_KEY` | Mặc định `openai/gpt-oss-20b` (không cần `LLM_MODEL` trong `.env`) |
| **Docker env** | `LLM_BASE_URL`/`LLM_MODEL` trong `.env` | Ví dụ Ollama trên host: `http://host.docker.internal:11434/v1` |
| **Kaggle / URL** | URL OpenAI-compatible bất kỳ + API key | Nếu là RedLine Ollama gateway: có catalog, tải model kèm tiến trình, xóa model |

Model nổi bật (kiểm tra bằng `python scripts/model_check.py --probe --ollama`):

- Groq (có tool calling): `openai/gpt-oss-20b` (nhẹ, mặc định), `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`.
  Groq hiện không có Llama chat model — dùng Llama qua Ollama.
- Ollama/Kaggle (nhẹ): `qwen3.5:4b`, `qwen3:4b`, `qwen3.5:9b`, `qwen3:8b`, `qwen2.5:7b`,
  `llama3.2:3b`, `llama3.1:8b`; lớn hơn: `qwen2.5:14b`, `gpt-oss:20b`.

Đổi model áp dụng cho toàn bộ target (giống đổi guardrail) và làm thay đổi `target_config_hash`.

**Host model trên Kaggle** — [`notebooks/kaggle_ollama_gateway.ipynb`](notebooks/kaggle_ollama_gateway.ipynb):

1. Attach Secrets `NGROK_AUTH_TOKEN` và `GATEWAY_TOKEN` (≥ 16 ký tự; nếu thiếu notebook tự sinh và in một lần).
2. Chạy các cell; khi `ready`, notebook in **Base URL** (`https://…ngrok…/v1`).
3. Trên web: **Kaggle / URL** → dán Base URL + token → **Kết nối** → tải model → **Dùng model này**.

Gateway ([`src/gateway/ollama_gateway.py`](src/gateway/ollama_gateway.py)) yêu cầu
`Authorization: Bearer <GATEWAY_TOKEN>` cho mọi route trừ `/health`:

```text
GET    /gateway/info              GPU, disk trống, version Ollama, model đang load
GET    /gateway/catalog           model nổi bật + installed + job đang tải
GET    /gateway/models            model đã cài
DELETE /gateway/models/{model}    xóa model
POST   /gateway/pulls {"model"}   bắt đầu tải (nền), trả job
GET    /gateway/pulls[/{id}]      state, status, completed, total, percent, speed_bps
DELETE /gateway/pulls/{id}        hủy tải
GET|POST /v1/...                  proxy OpenAI API của Ollama
```

Trình duyệt không gọi thẳng Kaggle: backend proxy qua `/config/llm/gateway/*`, token chỉ nằm
trong RAM của backend và không được trả ra API. Endpoint custom nhận URL do người dùng web nhập,
nên backend sẽ gửi request tới URL đó — chỉ mở web cho người tham gia thử nghiệm.

## 4. Gọi Chat API

Giao diện chat có bộ chọn **Agent / LLM thuần** ở thanh bên trái (trên điện thoại,
mở thanh bên bằng nút lịch sử). Đổi chế độ sẽ mở hội thoại mới; lịch sử lưu kèm
chế độ của từng phiên.

- **Agent** (mặc định): có thể gọi tool tra cứu RAG, đọc dữ liệu mock và tạo ticket.
- **LLM thuần**: gọi model trực tiếp với system prompt và lịch sử, không gửi tool
  definitions, không truy cập RAG/DB hay thực thi tool. Canary và guardrail vẫn áp dụng.

Cả `/chat` và `/v1/chat/completions` nhận trường `mode` là `agent` hoặc `llm`.
Ví dụ request LLM thuần tới `/chat`:

```json
{"message": "Giúp tôi soạn yêu cầu hỗ trợ", "mode": "llm"}
```

Gửi cùng `mode` và `session_id` ở các lượt tiếp theo. Chế độ được chọn theo request,
không thay đổi chế độ của người dùng khác. API `/chat` trả `mode` trong response;
OpenAI-compatible API trả trong `redline.mode` với response không streaming.

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

## 5. Dữ liệu mock

Seed hiện cung cấp nhiều customer, order và ticket giả lập với các trạng thái khác nhau.
Các ID ổn định như `CUS-001`, `ORD-001` và `TKT-001` có thể dùng trong test.

Kiểm tra số ticket trong PostgreSQL:

```bash
docker compose exec db psql -U redline -d redline -c "SELECT count(*) FROM tickets;"
```

Sau khi yêu cầu agent tạo ticket, chạy lại câu lệnh trên hoặc query ticket ID được trả
về để xác minh side effect thực sự xảy ra trong sandbox.

## 6. RAG corpus và ingestion

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

## 7. Chạy test

Cài môi trường Python cục bộ:

```bash
uv sync --locked
```

Kích hoạt trên PowerShell:

```powershell
uv run --locked pytest -q
```

Linux/macOS:

```bash
uv run --locked pytest -q
```

Các test agent/API dùng mock LLM và không được tiêu tốn quota hoặc cần kết nối mạng.

## 8. Audit log

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

## 9. Giới hạn hiện tại

- Đây là target red-team trong sandbox, không phải cấu hình production.
- Session chỉ nằm trong RAM và chưa phải cơ chế xác thực/phân quyền.
- Toàn bộ customer/order/ticket là dữ liệu giả lập.
- RAG là lexical retriever deterministic, chưa phải semantic vector search.
- `create_ticket` chỉ ghi Customer DB mock; agent không thể thanh toán, hoàn tiền, hủy
  đơn, gửi email/SMS hoặc gọi hệ thống thật.
- Corpus thử indirect prompt injection phải nằm ngoài corpus bình thường.

Các đặc tả liên quan nằm trong `docs/target-spec.md`, `docs/architecture.md`,
`docs/asset-inventory.md` và `docs/rag-corpus.md`.
