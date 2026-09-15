"""CLI for deterministic local RAG ingestion."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.services.rag_service import CORPUS_DIR, ingest_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RedLine local RAG index")
    parser.add_argument("corpus_dir", nargs="?", type=Path, default=CORPUS_DIR)
    args = parser.parse_args()
    manifests = ingest_corpus(args.corpus_dir)
    print(f"Ingestion complete: documents={len(manifests)}, chunks={sum(item.chunk_count for item in manifests)}")


if __name__ == "__main__":
    main()
