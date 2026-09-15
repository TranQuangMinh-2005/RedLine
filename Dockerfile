FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_DEV=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY src/ ./src/
COPY guardrails/ ./guardrails/
COPY data/ ./data/
COPY scripts/ ./scripts/

EXPOSE 8000

CMD ["sh", "-c", ".venv/bin/python -m src.ingestion.seed_data && .venv/bin/python scripts/ingest_rag.py && exec .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000"]
