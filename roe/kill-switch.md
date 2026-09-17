# Kill-switch — Dừng khẩn cấp

## Cơ chế

Target kiểm tra biến môi trường `ROE_KILL_SWITCH` ở đầu mỗi request tới `/chat` và
`/v1/chat/completions`. Khi `true`, target trả **HTTP 503 "kill-switch active"** ngay lập tức,
**không gọi LLM và không chạy tool** — nên không tốn token và không gây tác dụng phụ.

Nguồn enforce: `src/api/routers/chat.py` và `src/api/routers/openai_compat.py`
(`if settings.ROE_KILL_SWITCH: raise HTTPException(503, ...)`).

## Kích hoạt

```bash
# Đặt ROE_KILL_SWITCH=true trong .env rồi tạo lại container:
#   (compose đọc .env; biến shell rời KHÔNG được truyền vào service target)
sed -i 's/^ROE_KILL_SWITCH=.*/ROE_KILL_SWITCH=true/' .env
docker compose up -d target

# Dừng cứng toàn bộ sandbox (chắc chắn nhất):
docker compose down
```

Đã kiểm chứng: với `ROE_KILL_SWITCH=true`, `POST /chat` trả **HTTP 503 `kill-switch active`**;
với `false` trả 200. (Kiểm chứng bằng biến môi trường truyền trực tiếp vào tiến trình app, vì
`docker compose` chỉ nạp biến này từ `.env`, không nhận biến shell rời.)

## Khi nào kích hoạt

- Dữ liệu thật (PII/secret ngoài mock) lọt vào sandbox.
- Target gửi request tới host ngoài `roe/allowlist.yml`.
- Chi phí token/tiền vượt ngân sách trong RoE.
- Mentor VinSOC (người phê duyệt) yêu cầu dừng.

## Xác minh kill-switch còn hoạt động

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' -d '{"mode":"llm","message":"test"}'
# Kỳ vọng: 503 khi kill-switch bật; 200 khi tắt.
```

## Người chịu trách nhiệm

Người thực hiện kích hoạt ngay khi phát hiện dấu hiệu; báo Mentor VinSOC trong thời gian sớm nhất.
