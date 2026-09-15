"""CLI for deterministic local RAG ingestion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Đảm bảo root directory của project có trong sys.path khi chạy script trực tiếp
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.services.rag_service import CORPUS_DIR, ingest_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RedLine local RAG index")
    parser.add_argument("corpus_dir", nargs="?", type=Path, default=CORPUS_DIR)
    args = parser.parse_args()
    manifests = ingest_corpus(args.corpus_dir)
    print(f"Ingestion complete: documents={len(manifests)}, chunks={sum(item.chunk_count for item in manifests)}")


if __name__ == "__main__":
    main()
