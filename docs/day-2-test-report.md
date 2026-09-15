# Day 2 independent test report

Date: 2026-09-15

Scope: tasks 2.1-2.9
Tester boundary: `tests/**` and this report; no implementation files were changed by the tester.

## Result

The behavioral acceptance suite has been written, but it has **not been executed** in this workspace because no usable Python, pytest, or Docker runtime is installed. Day 2 therefore remains runtime-unverified; static inspection alone is not a pass decision.

## Coverage added

| Requirement | Automated coverage | Static status |
|---|---|---|
| 2.1 Chat API | health, request/response contract, validation, generated session ID, provider 502 sanitization, kill switch, model override ignored, session limit | Implemented; unexecuted |
| 2.2 Multi-turn | turn ordering, turn-2 history, session isolation, defensive copies, clear, limit, concurrent append | Implemented; unexecuted |
| 2.3 RAG | ranked retrieval, provenance, empty result, top-k, missing index, deterministic output | Implemented; unexecuted |
| 2.4 Ingestion | manifest/index, duplicate ID, required corpus metadata, minimum corpus coverage | Implemented; unexecuted |
| 2.5 Customer DB | schema/seed, 10+ customers, 20+ orders, 12+ tickets, status diversity, mock PII, idempotency, foreign keys, rollback | Implemented; unexecuted |
| 2.6 Read tools | success/not-found/input boundaries, bounded output, RAG provenance, allowlist and schema/registry sync | Implemented; unexecuted |
| 2.7 Side effect | persistent DB count delta, record read-back, validation/no-write, unknown customer/no-write, idempotency | Implemented; unexecuted |
| 2.8 Logging | recursive redaction, parseable JSON, correlation fields/context, LLM/tool/retrieval event sequence and failure event | Implemented; unexecuted |
| 2.9 README | Commands and documentation updated by the coordinator; clean-machine walkthrough not possible without Docker | Static review only |

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

## Runtime blockers

Commands attempted:

```text
pytest -q
python -m pytest -q
where.exe python
where.exe py
where.exe docker
```

Observed environment:

- `pytest` is not on PATH.
- `python.exe` resolves only to the Microsoft Store application alias and cannot execute Python.
- `py` is absent.
- `docker` is absent.

Consequently, the following evidence is still mandatory before marking Day 2 done:

1. A clean `python -m pytest -q` run with all tests passing.
2. `docker compose config`, build, startup, and health-check evidence.
3. A Docker E2E run showing RAG retrieval, customer/ticket reads, and `create_ticket` persisting one new ticket.
4. A two-turn `/chat` request plus a second isolated session.
5. JSON log evidence for one complete request, verified not to contain API key, canary, email, phone, or address.
6. A clean-machine README walkthrough by another team member.

## Commands to run in a prepared environment

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Do not use a real customer dataset or production integration during acceptance.
