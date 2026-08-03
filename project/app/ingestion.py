"""
ingest.py — orchestration only. No embedding logic, no Qdrant logic here.
Walks a repo, chunks every .py file, embeds chunks, stores them in Qdrant.

Usage (keys are read from .env automatically, or pass --jina-key):

    Local embedded Qdrant (no server needed, data saved under ./qdrant_data):
        python -m app.ingestion <repo_path> --local
        python -m app.ingestion <repo_path> --local --qdrant-dir ./qdrant_data

    Qdrant server:
        python -m app.ingestion <repo_path> --qdrant-url http://localhost:6333

    Both support: --collection <name>

Offline wiring check (no keys, no server): python test_pipeline.py
"""

import argparse
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from app.chunking import PythonChunker
from app.config import load_env
from app.embedder import Embedder
from app.vector_db import VectorDB

DEFAULT_QDRANT_DIR = "qdrant_data"
DEFAULT_COLLECTION = "code_chunks"


def ingest(
    repo_path: str,
    jina_api_key: str,
    collection_name: str = DEFAULT_COLLECTION,
    qdrant_url: str | None = None,
    local_path: str | None = None,
):
    """Chunk every .py file under repo_path, embed the chunks, store them in Qdrant.

    Vector DB is either a local embedded store (local_path) or a running
    Qdrant server (qdrant_url). Exactly one must be provided.
    """
    if local_path:
        client = QdrantClient(path=local_path)
    elif qdrant_url:
        client = QdrantClient(url=qdrant_url)
    else:
        raise ValueError("Provide either --local (embedded Qdrant) or --qdrant-url (server).")

    chunker = PythonChunker()
    embedder = Embedder(api_key=jina_api_key)
    vector_db = VectorDB(client=client)

    # 1. Find all .py files in the repo
    py_files = list(Path(repo_path).rglob("*.py"))
    print(f"Found {len(py_files)} Python files in {repo_path}")

    # 2. Chunk every file
    all_chunks = []
    for file_path in py_files:
        try:
            all_chunks.extend(chunker.chunk_file(str(file_path)))
        except Exception as e:
            # Don't let one bad file kill the whole ingestion run —
            # but DO surface it loudly, don't swallow silently.
            print(f"  [SKIPPED - parse error] {file_path}: {e}")

    print(f"Total chunks extracted: {len(all_chunks)}")

    if not all_chunks:
        print("No chunks found — stopping before touching embedder/Qdrant.")
        return

    # 3. Embed all chunks in one batched call
    #    ponytail: one request for the whole repo — Jina caps batches at ~2048 inputs,
    #    so very large repos will need this looped in chunks-of-chunks.
    texts = [c.text for c in all_chunks]
    print(f"Embedding {len(texts)} chunks...")
    embeddings = embedder.embed_chunks(texts)

    if len(embeddings) != len(all_chunks):
        raise RuntimeError(
            f"Mismatch: {len(all_chunks)} chunks but {len(embeddings)} embeddings returned. "
            "Stopping — do not store misaligned data."
        )

    # 4. Create the collection sized to the model's real output dim.
    #    (Chunk.id is already a deterministic UUID, valid as a Qdrant point id.)
    vector_size = len(embeddings[0])
    print(f"Embedding dimension detected: {vector_size}")
    vector_db.create_collection(collection_name, vector_size=vector_size)

    # 5. Store everything
    vector_db.store_embeddings(collection_name, all_chunks, embeddings)

    print(f"\nIngestion complete: {len(all_chunks)} chunks stored in '{collection_name}'.")

    # 6. Sanity check — does Qdrant's reported count match what we sent?
    count = vector_db.client.count(collection_name).count
    print(f"Qdrant reports {count} points in collection (expected {len(all_chunks)}).")
    if count != len(all_chunks):
        print("  WARNING: mismatch — investigate before trusting this collection.")


def main(argv: list[str] | None = None) -> int:
    load_env()  # read groq_api_key / jina_api_key from .env when not already set

    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion",
        description="Chunk + embed + store a Python codebase into Qdrant.",
    )
    parser.add_argument("repo_path", help="Path to the codebase/repo to ingest")
    parser.add_argument(
        "--local",
        nargs="?",
        const=DEFAULT_QDRANT_DIR,
        metavar="DIR",
        help="Use local embedded Qdrant (default dir: ./qdrant_data). No server needed.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant server URL (e.g. http://localhost:6333) instead of --local",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--jina-key",
        default=None,
        help="Jina API key (defaults to jina_api_key from .env)",
    )
    args = parser.parse_args(argv)

    if args.local and args.qdrant_url:
        parser.error("Use either --local or --qdrant-url, not both.")

    jina_api_key = args.jina_key or os.environ.get("jina_api_key")
    if not jina_api_key:
        print("No Jina API key found. Set jina_api_key in .env or pass --jina-key.")
        return 2

    try:
        ingest(
            repo_path=args.repo_path,
            jina_api_key=jina_api_key,
            collection_name=args.collection,
            qdrant_url=args.qdrant_url,
            local_path=args.local,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
