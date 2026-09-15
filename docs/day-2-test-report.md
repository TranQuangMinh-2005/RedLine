# Day 2 independent test report

Date: 2026-09-15

Scope: tasks 2.1-2.9
Tester boundary: `tests/**` and this report; no implementation files were changed by the tester.

## Result

The automated acceptance suite passes in the uv-managed Python environment: **78 passed in 1.19s**. All LLM behavior is mocked, so the suite consumes no API quota.

## Coverage added

| Requirement | Automated coverage | Static status |
|---|---|---|
| 2.1 Chat API | health, request/response contract, validation, generated session ID, provider 502 sanitization, kill switch, model override ignored, session limit | Passed |
| 2.2 Multi-turn | turn ordering, turn-2 history, session isolation, defensive copies, clear, limit, concurrent append | Passed |
| 2.3 RAG | ranked retrieval, provenance, empty result, top-k, missing index, deterministic output | Passed |
| 2.4 Ingestion | manifest/index, duplicate ID, required corpus metadata, minimum corpus coverage | Passed |
| 2.5 Customer DB | schema/seed, 10+ customers, 20+ orders, 12+ tickets, status diversity, mock PII, idempotency, foreign keys, rollback | Passed |
| 2.6 Read tools | success/not-found/input boundaries, bounded output, RAG provenance, allowlist and schema/registry sync | Passed |
| 2.7 Side effect | persistent DB count delta, record read-back, validation/no-write, unknown customer/no-write, idempotency | Passed |
| 2.8 Logging | recursive redaction, parseable JSON, correlation fields/context, LLM/tool/retrieval event sequence and failure event | Passed |
| 2.9 README | uv commands and dependency-lock workflow documented; clean-machine Docker walkthrough remains pending | Automated suite passed |

Test files:

- `tests/test_chat_api.py`
- `tests/test_session_store.py`
- `tests/test_rag_service.py`
- `tests/test_db.py`
- `tests/test_customer_tools.py`
- `tests/test_side_effect_tool.py`
- `tests/test_agent_integration.py`
- `tests/test_logging.py`

All LLM behavior in the new tests is mocked. The suite must not consume API quota or require network access.

## Static evidence collected

- `src/main.py` exposes `/health` and includes the stateful chat router.
- Client request schema has no model field; an extra client `model` value is not forwarded to the agent.
- Agent has a finite tool loop and an allowlisted registry containing the four Day 2 tools.
- Agent emits `llm_completed`, `tool_called`, `retrieval_started`, `retrieval_completed`, `tool_completed`, and `tool_failed` as applicable.
- Seed constants contain 10 customers, 20 orders, and 12 tickets; order/ticket statuses meet the requested diversity.
- Approved corpus directory contains 14 Markdown documents with provenance metadata.
- `.gitignore` ignores legacy raw research documents and generated `index.json`/`manifest.jsonl`, while allowing approved paraphrased documents under `data/rag/documents/*.md`.
- No `TODO: W1 task 2.1-2.8` marker remains under `src/`.
- `git diff --check` reports no whitespace errors (only Windows LF-to-CRLF notices).

## Runtime evidence and remaining blockers

Automated test command:

```text
uv run --locked pytest -q
```

Result: `78 passed in 1.19s`.

`uv` manages the project interpreter and environment, so a separately installed Python and `pip` are not required. The uv-managed virtual environment intentionally does not need to expose `pip`.

Observed remaining limitation:

- `docker` is absent.

Consequently, the following Docker/manual evidence is still pending:

1. `docker compose config`, build, startup, and health-check evidence.
2. A Docker E2E run showing RAG retrieval, customer/ticket reads, and `create_ticket` persisting one new ticket.
3. A two-turn `/chat` request plus a second isolated session.
4. JSON log evidence for one complete request, verified not to contain API key, canary, email, phone, or address.
5. A clean-machine README walkthrough by another team member.

## Commands to run in a prepared environment

```powershell
uv sync --locked
uv run --locked pytest -q
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Do not use a real customer dataset or production integration during acceptance.
