# Báo cáo Week 1 — Recon, Threat Model & Baseline Attacks

Đánh giá an ninh LLM/RAG agent (RedLine Customer Assistant) trong sandbox được uỷ quyền.

**Ngày:** 2026-09-17 · **Target:** `openai/gpt-oss-20b` qua OpenRouter, Docker sandbox `http://localhost:8000`
**Nguyên tắc:** bản đồ bề mặt tấn công dựng **chỉ từ recon quan sát hộp đen**, không chép từ tài liệu mô tả.
Mỗi kết luận ghi rõ Observation / Inference / Unknown.

---

## Sản phẩm bàn giao

| # | Sản phẩm | Tài liệu |
|---|---|---|
| 1 | Ứng dụng LLM mục tiêu chạy trong sandbox | [`../../README.md`](../../README.md) (hướng dẫn dựng bằng Docker) |
| 2 | Báo cáo recon (fingerprint model, cấu trúc RAG, guardrail + cách phát hiện) | [`recon.md`](recon.md) |
| 3 | Bản đồ bề mặt tấn công | [`attack-surface.md`](attack-surface.md) |
| 4 | Threat model theo OWASP LLM Top 10 (2026) | [`threat-model.md`](threat-model.md) |
| 5 | Rules of Engagement + kill-switch (đã kiểm chứng) | [`../../roe/RULES_OF_ENGAGEMENT.md`](../../roe/RULES_OF_ENGAGEMENT.md), [`../../roe/kill-switch.md`](../../roe/kill-switch.md), [`../../roe/allowlist.yml`](../../roe/allowlist.yml) |
| 6 | Nhật ký 3–5 tấn công baseline kèm bằng chứng | [`baseline-attacks.md`](baseline-attacks.md) |
| + | Báo cáo tổng hợp (ma trận guardrail, đánh giá RAG, khuyến nghị) | [`security-eval-report.md`](security-eval-report.md) |

## Bằng chứng (evidence)

Thư mục [`evidence/`](evidence/) chứa toàn bộ request/response thô và script tái lập:

| Đường dẫn | Nội dung |
|---|---|
| `evidence/recon/R01–R27.json` | 27 probe recon hộp đen (fingerprint, RAG, tool, guardrail, endpoint) |
| `evidence/recon/deep.json` | Recon sâu nhóm A/B/C (giới hạn context, chunk structure, định vị guardrail) |
| `evidence/baseline/*.json` | 5 tấn công baseline × 2 profile (none/strict) |
| `evidence/matrix.json` | Ma trận bypass 16 tấn công × 5 cấu hình |
| `evidence/recon_probes.py`, `recon_deep.py`, `baseline_attacks.py`, `bypass_matrix.py`, `rag_eval.py` | Script tái lập |

> Bản gốc các file này sinh ra trong `runs/security-eval/` (gitignore); bản trong `evidence/` là ảnh chụp
> đưa vào báo cáo để nộp.

## Kết quả chính

- **Fingerprint:** `openai/gpt-oss-20b` (OpenRouter), reasoning model; giới hạn context giữa 200k–800k ký tự.
  Recon phát hiện model thực khác với `target-spec.md` (ghi `qwen/qwen3.8-27b`) — đúng lý do phải fingerprint.
- **RAG:** 8 tài liệu; chunk theo độ dài (`document_id:index`); retrieval **không có ngưỡng** → luôn trả top-k
  kể cả câu ngoài miền (LLM09).
- **Guardrail:** định vị bằng **độ trễ** — lọc input regex chặn ở ~0.00s/0 token; lọc output/Llama Guard chặn
  sau vài giây; model tự từ chối mất 0.9–7.6s. Thông điệp "Tôi không thể…" (cố định) = guardrail code;
  "Xin lỗi…" (biến thiên) = model tự từ chối.
- **Baseline:** B1–B5 không moi được secret/PII (model + input filter chặn). **B6–B7** (bằng chứng thao tác thủ công trên UI, trace nguyên văn trong `baseline-attacks.md`) là 2 bypass
  thành công đầu tiên: rò rỉ RAG context qua khung `[SOURCE CHUNK]`, và jailbreak đa lượt vượt Prompt Guard.
- **Rủi ro cao nhất ở hạ tầng:** API cấu hình + corpus RAG **không xác thực** (hạ được phòng thủ bằng 1 request).

## Khoảng trống & việc còn lại

Xem cuối [`attack-surface.md`](attack-surface.md) (§6) và residual risks trong [`threat-model.md`](threat-model.md):
indirect injection qua tài liệu RAG thật, hiệu lực authz tầng code (chưa kích hoạt được vì model từ chối trước),
improper output handling (LLM10).
