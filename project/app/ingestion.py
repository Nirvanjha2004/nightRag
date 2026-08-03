"""
ingest.py — orchestration only. No embedding logic, no Qdrant logic here.
Walks a repo, chunks every .py file, embeds chunks, stores them in Qdrant.

Usage:
    python -m app.ingestion <repo_path> <qdrant_url> <jina_api_key> [collection_name]

Offline wiring check (no keys, no server): python test_pipeline.py
"""

import sys
from pathlib import Path

from qdrant_client import QdrantClient

from app.chunking import PythonChunker
from app.embedder import Embedder
from app.vector_db import VectorDB


def ingest(repo_path: str, qdrant_url: str, jina_api_key: str, collection_name: str = "code_chunks"):
    """Chunk every .py file under repo_path, embed the chunks, store them in Qdrant."""
    chunker = PythonChunker()
    embedder = Embedder(api_key=jina_api_key)
    vector_db = VectorDB(client=QdrantClient(url=qdrant_url))

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
    args = argv if argv is not None else sys.argv[1:]

    if len(args) not in (3, 4):
        print(__doc__)
        return 2

    repo_path, qdrant_url, jina_api_key = args[0], args[1], args[2]
    collection_name = args[3] if len(args) == 4 else "code_chunks"

    ingest(repo_path, qdrant_url, jina_api_key, collection_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
