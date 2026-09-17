# Rules of Engagement (RoE) — RedLine LLM/RAG Security Evaluation

**Phiên bản:** 1.0 · **Ngày hiệu lực:** 2026-09-17 · **Target commit:** `9ee5ac5`
**Loại đánh giá:** red-team hộp đen ứng dụng LLM/RAG trong sandbox, được uỷ quyền.

Tài liệu này ràng buộc mọi hoạt động tấn công/thử nghiệm. Giá trị giới hạn dưới đây **khớp với cấu hình
đang được enforce trong code** (`src/config.py`, `roe/allowlist.yml`), không phải cam kết suông.

---

## 1. Người phê duyệt & trách nhiệm

| Vai trò | Người | Trách nhiệm |
|---|---|---|
| **Phê duyệt RoE** | Mentor VinSOC | Duyệt phạm vi, ký xác nhận trước khi test |
| Người thực hiện | Nhóm red team RedLine | Tuân thủ RoE, ghi log đầy đủ |
| Chủ sở hữu sandbox | Nhóm dự án | Vận hành target, giữ dữ liệu mock |

**Ô ký xác nhận:**

```
Phê duyệt bởi (Mentor VinSOC): ______________________   Ngày: __________
Người thực hiện:               ______________________   Ngày: __________
```

---

## 2. Phạm vi được phép (IN SCOPE)

- **Chỉ một target:** `http://target:8000` trong docker-compose sandbox (khi test từ host: `http://localhost:8000`).
  Nguồn: [`roe/allowlist.yml`](allowlist.yml).
- Các chốt phòng thủ local đi kèm sandbox: `llama-guard` (:8088), `prompt-guard` (:8089) — chỉ để quan sát
  hành vi phòng thủ, không phải mục tiêu khai thác riêng.
- Kỹ thuật cho phép: prompt injection (trực tiếp/gián tiếp), trích xuất system prompt/secret, thử vượt
  quyền tool (BOLA-like), đầu độc/injection qua RAG, đo bypass guardrail, fingerprint, recon endpoint.
- Đọc/ghi cấu hình runtime của target (`/config/*`) **chỉ để phục vụ đo lường** (đổi profile, bật/tắt guard),
  luôn đưa về mặc định sau khi xong.

## 3. Mục tiêu bị cấm (OUT OF SCOPE)

- **Mọi host ngoài allowlist** — tuyệt đối cấm (`*.vinuni.edu.vn`, `*.vinsoc.vn`, và `*` mặc định).
- Nhà cung cấp LLM phía sau (OpenRouter/Groq/Kaggle) và hạ tầng của họ — không tấn công, chỉ dùng như
  dịch vụ backend hợp pháp của target.
- Không tấn công tính khả dụng theo kiểu phá hoại: không flood để làm sập, không xoá corpus RAG hàng loạt,
  không làm hỏng DB.
- Không khai thác để thoát sandbox (container escape, truy cập host).

## 4. Dữ liệu không được sử dụng

- **Không dùng dữ liệu khách hàng thật.** Sandbox chỉ chứa dữ liệu mock (`CUS-xxx`, `@example.test`,
  số điện thoại `0900000xxx`) và 8 tài liệu chính sách công khai.
- Không nạp dữ liệu cá nhân/PII thật vào RAG hay hội thoại.
- Không sao chép secret/canary của target ra ngoài môi trường đánh giá; khi ghi report, canary phải được
  thay bằng `[CANARY]`.

## 5. Giới hạn tần suất & ngân sách (đang được enforce)

| Giới hạn | Giá trị | Nơi enforce |
|---|---|---|
| Request/phút mỗi actor | **30** | `ROE_MAX_REQUESTS_PER_MIN`, trả HTTP 429 khi vượt |
| Tổng token mỗi actor | **500.000** | `ROE_MAX_TOKENS_TOTAL`, HTTP 429 |
| Số vòng gọi tool mỗi request | **5** | `ROE_MAX_ATTEMPTS`, trả thông báo "đạt giới hạn công cụ" |
| Số message mỗi session | **50** | `InMemorySessionStore`, HTTP 429 |
| **Ngân sách tiền OpenRouter** | ≤ **$5** cho toàn đợt đánh giá | Theo dõi thủ công qua `/api/v1/key` (usage) |

- Script tự động phải giữ nhịp ≥ 2 giây/request để không chạm trần 30 req/phút.
- Nếu chạm ngân sách token/tiền: **dừng**, báo người phê duyệt trước khi tiếp tục.

## 6. Cơ chế dừng khẩn cấp (kill-switch)

Xem chi tiết [`roe/kill-switch.md`](kill-switch.md). Tóm tắt: đặt `ROE_KILL_SWITCH=true` → target trả
HTTP 503 cho mọi request `/chat` và `/v1/chat/completions` ngay lập tức, không gọi LLM.

Kích hoạt kill-switch khi: phát hiện dữ liệu thật lọt vào sandbox, target gọi ra ngoài allowlist, chi phí
vượt ngân sách, hoặc người phê duyệt yêu cầu dừng.

## 7. Ghi log & bằng chứng bắt buộc

- Mọi tấn công lưu request + response nguyên văn (evidence file), kèm `target_config_hash`.
- Ghi rõ Observation vs Inference; không kết luận vượt quá bằng chứng.
- Trạng thái phòng thủ (profile, guard) phải được chốt và ghi lại ở đầu/cuối mỗi phép đo.

## 8. Khôi phục sau đánh giá

- Đưa target về mặc định: `DEFENSE_PROFILE=none`, Prompt Guard tắt, Llama Guard tắt.
- Ghi nhận minh bạch mọi tác dụng phụ còn lại (ví dụ ticket do probe tạo mà không có API xoá).
