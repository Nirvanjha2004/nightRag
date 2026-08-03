"""
ingest.py — orchestration only. No embedding logic, no Qdrant logic here.
Walks a repo, chunks every .py file, embeds chunks, stores them in Qdrant.

Usage:
    python ingest.py <repo_path> <qdrant_url> <jina_api_key> [collection_name]
"""

import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient

from chunker import PythonChunker
from embedder import Embedder
from vector_db import VectorDB


def stable_point_id(chunk_id: str) -> str:
    """Qdrant point IDs must be int or UUID — derive a deterministic UUID
    from our readable chunk_id (file_path:start_line) so re-ingestion is
    idempotent (same chunk -> same point id -> upsert overwrites, not duplicates)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def ingest(repo_path: str, qdrant_url: str, jina_api_key: str, collection_name: str = "code_chunks"):
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
            chunks = chunker.chunk_file(str(file_path))
            all_chunks.extend(chunks)
        except Exception as e:
            # Don't let one bad file kill the whole ingestion run —
            # but DO surface it loudly, don't swallow silently.
            print(f"  [SKIPPED - parse error] {file_path}: {e}")

    print(f"Total chunks extracted: {len(all_chunks)}")

    if not all_chunks:
        print("No chunks found — stopping before touching embedder/Qdrant.")
        return

    # 3. Create collection (size must match your Jina model's output dim —
    #    check this against the actual model you're using, 1536 is a placeholder
    #    default in VectorDB and may not match jina-embeddings-v5-text-small)
    sample_embedding = embedder.embed_query("test")
    vector_size = len(sample_embedding)
    print(f"Embedding dimension detected: {vector_size}")
    vector_db.create_collection(collection_name, vector_size=vector_size)

    # 4. Batch embed all chunks (one API call instead of N)
    texts = [c.text for c in all_chunks]
    print(f"Embedding {len(texts)} chunks...")
    embeddings = embedder.embed_chunks(texts)

    if len(embeddings) != len(all_chunks):
        raise RuntimeError(
            f"Mismatch: {len(all_chunks)} chunks but {len(embeddings)} embeddings returned. "
            "Stopping — do not store misaligned data."
        )

    # 5. Attach stable Qdrant-safe point IDs and store
    #    (VectorDB.store_embeddings uses chunk.id as the point id directly —
    #     we need to swap that for a UUID derived from the readable id first)
    for c in all_chunks:
        c.id = stable_point_id(c.id) if not _looks_like_uuid(c.id) else c.id

    vector_db.store_embeddings(collection_name, all_chunks, embeddings)

    print(f"\nIngestion complete: {len(all_chunks)} chunks stored in '{collection_name}'.")

    # 6. Sanity check — does Qdrant's reported count match what we sent?
    count = vector_db.client.count(collection_name).count
    print(f"Qdrant reports {count} points in collection (expected {len(all_chunks)}).")
    if count != len(all_chunks):
        print("  WARNING: mismatch — investigate before trusting this collection.")


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
