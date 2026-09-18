# Báo cáo cải thiện guardrail bằng code

**Ngày thực hiện:** 2026-09-16

**Target:** RedLine Customer Support Agent, fixed user `CUS-001`

**Phạm vi:** Docker sandbox được cấp phép; không áp dụng cho hệ thống nghiệp vụ thật

## 1. Mục tiêu

Thay đổi này chuyển các security invariant quan trọng từ mức “yêu cầu model tuân theo
system prompt” sang cơ chế deterministic trong code, đồng thời giữ ba level phục vụ
benchmark:

- `none`: baseline yếu có chủ đích, chỉ được dùng trong sandbox.
- `basic`: guardrail code mức cơ bản, ưu tiên authorization và low-cost controls.
- `strict`: defense-in-depth gồm input, RAG, action, tool authorization và output.

Tên runtime vẫn là `none/basic/strict` để không phá API và dữ liệu benchmark cũ.
Trong báo cáo, ba tên này tương ứng với **baseline/base/strict**.

## 2. Căn cứ thiết kế

Các quyết định dựa trên các nguyên tắc sau:

1. System prompt không phải security boundary và không được dùng thay authorization.
2. Quyền truy cập phải deny-by-default và được kiểm tra bằng code tại thời điểm action.
3. LLM chỉ đề xuất tool call; policy code quyết định có thực thi hay không.
4. Nội dung RAG là untrusted data, không phải instruction.
5. Cần phân biệt raw model leakage với leakage thực sự được giao cho người dùng.

Nguồn tham khảo chính:

- [OWASP LLM07: System Prompt Leakage](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/)
  — security controls phải độc lập với LLM.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
  — deny-by-default và kiểm tra mọi request.
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)
  — tách proposal khỏi execution, validate tool call.
- [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html)
  — scan ingestion/retrieval và đánh dấu untrusted content.
- [OWASP LLM05: Improper Output Handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)
  — model output phải được validate trước khi dùng.
- [NIST AI 600-1](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
  — áp dụng test, evaluation, validation và verification lặp lại, có tài liệu evidence.

## 3. Profile matrix sau cải thiện

| Control | `none` / baseline | `basic` / base | `strict` |
|---|---:|---:|---:|
| Input filter | off | basic rules | basic + strict rules |
| Prompt hardening | off | on | enhanced |
| Canary check | off | normalized | normalized + encoded output |
| Fixed-customer tool authorization | off | on | on |
| Server-bound ticket idempotency | off | on | on |
| RAG trust annotation | off | on | on |
| RAG suspicious-chunk quarantine | off | off | on |
| Per-tool call policy | off | off | on |
| Explicit create-ticket intent | off | off | required |
| Sensitive output filter | off | off | on |

`none` vẫn giữ lỗ hổng authorization có chủ đích để đo baseline. Cấu hình này không
phải cấu hình có thể deploy ngoài sandbox.

## 4. Thay đổi implementation

### 4.1 Tool action policy

Thêm `src/guardrails/action_policy.py` làm policy enforcement point trước tool
execution.

Các rule:

- `basic` và `strict` từ chối `get_customer_info`/`create_ticket` nếu customer khác
  `CUS-001`.
- `get_ticket` tiếp tục kiểm tra ownership trong tool layer sau khi đọc record.
- `strict` giới hạn số lần gọi theo từng tool.
- `strict` không cho `create_ticket` nếu turn hiện tại không có explicit write intent.
- Idempotency key của `create_ticket` trong profile được bảo vệ được ghi đè bằng
  `request_id` do server tạo; model không tự chọn key.
- Tool ngoài policy bị fail closed ở `strict`.

### 4.2 RAG trust boundary

Thêm `src/guardrails/rag_filter.py` xử lý kết quả `search_knowledge` trước khi đưa
vào model:

- `none`: giữ nguyên raw result để làm baseline.
- `basic`: thêm `trust_level=untrusted_retrieved_data` vào từng chunk.
- `strict`: chuẩn hóa Unicode, phát hiện instruction override, authority marker,
  role override và secret-exfiltration pattern; chunk đáng ngờ bị loại khỏi context.
- Nếu toàn bộ chunk bị loại, tool result có status `blocked` thay vì đưa nội dung đó
  cho model.

Đây là deterministic fast layer, không được xem là giải pháp tuyệt đối cho semantic
prompt injection. Seed library phải tiếp tục kiểm tra các bypass không có keyword.

### 4.3 Output guardrail

Strict output filter được bổ sung decode best-effort Base64/hex và chặn nếu decoded
content chứa canary. Basic vẫn chỉ dùng canary normalization để tạo khác biệt có
kiểm soát giữa hai level.

### 4.4 Leakage evidence

Native chat response và OpenAI-compatible metadata có thêm:

- `raw_canary_detected`: model từng sinh canary trước output filter.
- `delivered_canary_detected`: response cuối thực sự còn canary hay không.
- `canary_leaked`: giữ tương thích cũ và phản ánh delivered leakage.

Nhờ đó có thể phân biệt “model bị compromise nhưng output guardrail cứu được” với
“không có leakage ngay từ model”.

### 4.5 Observability

Khi action/RAG policy can thiệp, audit log phát event `guardrail_action` cùng:

- `stage=tool_proposal` hoặc `stage=rag_retrieval`;
- `tool_name`;
- danh sách reason/action code.

Không log raw secret hay raw PII.

## 5. Security properties mong đợi

| Tình huống | Baseline | Basic | Strict |
|---|---|---|---|
| Model yêu cầu dữ liệu `CUS-002` | Có thể chạy | Code từ chối | Code từ chối |
| Model tạo ticket cho `CUS-002` | Có thể chạy | Code từ chối | Code từ chối |
| RAG chunk chứa instruction rõ ràng | Đưa nguyên vào context | Gắn untrusted label | Quarantine |
| RAG tự kích hoạt `create_ticket` | Có thể xảy ra | Chỉ được tạo cho CUS-001 | Bị giữ nếu user không yêu cầu rõ |
| Output chứa canary thường | Có thể giao ra | Bị canary check chặn | Bị chặn |
| Output chứa canary Base64 | Có thể giao ra | Có thể giao ra | Bị decode và chặn |
| Lặp cùng tool nhiều lần | Global loop limit | Global loop limit | Thêm per-tool limit |

## 6. Test evidence

Lệnh xác minh cuối:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Kết quả ngày 2026-09-16:

```text
104 passed in 3.76s
```

`git diff --check` không phát hiện whitespace error. Các module và test mới cũng vượt
qua Ruff. Toàn repository vẫn có lint debt cũ ở những file ngoài phạm vi thay đổi;
không tự động format toàn repository để tránh tạo diff không liên quan.

Automated test đã chứng minh:

1. `none` vẫn tạo được unsafe baseline trong sandbox.
2. `basic` chặn cross-customer bằng code, không phụ thuộc model refusal.
3. `strict` quarantine RAG injection marker.
4. `strict` giữ `create_ticket` nếu không có explicit user intent.
5. Server thay model-controlled idempotency key.
6. Strict chặn Base64-encoded canary nhưng basic không chặn.
7. Raw leakage vẫn được ghi nhận khi delivered output đã được filter.
8. Runtime profile endpoint trả đúng capability flags.

Khi chạy attack library, phải dùng session mới cho từng profile và lưu đồng thời:

- attack success;
- model refusal;
- input/output block;
- tool authorization denial;
- RAG quarantine action;
- raw và delivered leakage;
- latency/token/profile/config hash.

## 7. Residual risks

Các điểm chưa được giải quyết hoàn toàn trong lần cải thiện này:

- Regex/RAG marker không bắt được mọi semantic hoặc multilingual injection.
- Explicit write intent chưa phải quy trình confirmation hai bước có signed approval.
- Endpoint đổi profile và RAG management vẫn là benchmark control plane; phải chỉ
  expose trong sandbox/internal network.
- Output DLP đang dựa trên mock-data patterns, chưa phải enterprise PII classifier.
- System prompt và provider safety vẫn có thể khiến ASR giống nhau; cần phân tích
  prevention stage thay vì chỉ nhìn response cuối.

## 8. Khuyến nghị bước tiếp theo

1. Chạy lại bộ 12 baseline cũ vì báo cáo trước đã được tạo trước code authorization mới.
2. Chạy 70 seed trên `none`; chọn subset smoke test trên `basic/strict` trong Week 2.
3. Week 5 chạy cùng corpus trên cả ba profile và đo ASR, false-positive rate, raw leak,
   delivered leak, unauthorized tool execution và p95 latency.
4. Nếu strict vẫn bị bypass semantic injection, bổ sung classifier riêng như một lớp
   defense-in-depth; không thay thế deterministic authorization.
