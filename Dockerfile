FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY guardrails/ ./guardrails/
COPY data/ ./data/
COPY scripts/ ./scripts/

EXPOSE 8000

CMD ["sh", "-c", "python -m src.ingestion.seed_data && python scripts/ingest_rag.py && exec uvicorn src.main:app --host 0.0.0.0 --port 8000"]
