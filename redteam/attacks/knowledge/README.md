# Kho tri thức kỹ thuật (Tuần 2)

Kho tri thức nhỏ phục vụ thiết kế seed và review: 8 mã OWASP LLM Top 10 trong phạm vi,
5 kỹ thuật MITRE ATLAS đang dùng và 20 kỹ thuật tấn công đã biết, kèm chức năng tìm kiếm
theo tên kỹ thuật/alias/mã.

## Thành phần

| File | Vai trò |
|---|---|
| `knowledge_base.json` | Dữ liệu: `owasp_llm_top10`, `atlas`, `techniques` |
| `search.py` | Engine tìm kiếm deterministic + CLI (chỉ dùng stdlib) |
| `__init__.py` | Public API: `load_knowledge`, `load_entries`, `search_knowledge`, `find_by_id` |

Mỗi technique tham chiếu seed thật trong thư viện v3core qua `seed_refs`, map về
`category` trong `redteam/attacks/taxonomy/taxonomy.yml` và các mã `owasp_ids`/`atlas_ids`.
Test `tests/test_knowledge_search.py` kiểm tra chéo các ràng buộc này, nên dữ liệu không
thể lệch khỏi taxonomy hoặc seed library.

## Sử dụng

```powershell
# Tìm theo tên kỹ thuật hoặc alias (hỗ trợ tiếng Việt có/không dấu)
.\.venv\Scripts\python.exe -m redteam.attacks.knowledge.search "prompt injection"
.\.venv\Scripts\python.exe -m redteam.attacks.knowledge.search jailbreak

# Lọc theo loại entry, giới hạn kết quả, xuất JSON
.\.venv\Scripts\python.exe -m redteam.attacks.knowledge.search "role in prompt" --type technique --top 3
.\.venv\Scripts\python.exe -m redteam.attacks.knowledge.search LLM01 --json

# Tra cứu chính xác theo id
.\.venv\Scripts\python.exe -m redteam.attacks.knowledge.search --id TECH-RIP
```

Dùng như thư viện:

```python
from redteam.attacks.knowledge import search_knowledge

for score, entry in search_knowledge("indirect injection", top_k=3):
    print(score, entry["id"], entry["name"])
```

## Tiêu chí thành công Tuần 2

- Tìm `prompt injection` trả về LLM01, AML.T0051 và technique liên quan.
- Tìm `jailbreak` trả về AML.T0054 và `TECH-ROLEPLAY`.
- Kho có 10–20 ví dụ kỹ thuật (hiện tại: 20) và tìm kiếm được theo tên kỹ thuật.
- Bằng chứng chạy lệnh: `docs/Week2/supporting-documents/evidence/knowledge-search.txt`.

## Quy tắc thêm kỹ thuật mới

1. Chọn `id` dạng `TECH-<TÊN>`, ghi `category` đúng theo taxonomy hiện có.
2. Chỉ dùng `owasp_ids` trong 8 mã scope; `atlas_ids` chỉ dùng ID đã có trong `atlas`
   (không bịa ID mới — ID chưa verify thì để rỗng và ghi lý do trong `detection`).
3. `seed_refs` phải là ID có thật trong `seed_library_v3core_base.json` hoặc
   `seed_mutations_v3core.json`.
4. Chạy `pytest -q tests/test_knowledge_search.py` và `ruff check redteam/ tests/`.

## Nguồn

- OWASP Top 10 for LLM Applications 2025.
- MITRE ATLAS (`atlas.mitre.org`).
- Caesar Creek Software, *Attacking the GPT-OSS Model*.
- Jonathan Boice, *Hacking the 20B Beast*.
