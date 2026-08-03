"""
test_pipeline.py — offline end-to-end check of the RAG wiring.
No Jina key, no Groq key, no Qdrant server needed: a deterministic fake
embedder + in-memory Qdrant prove that chunk -> embed -> store -> retrieve
still work together.

Run: python test_pipeline.py   (from the project root)
"""

import hashlib

from qdrant_client import QdrantClient

from app.chunking import PythonChunker
from app.retriever import Retriever
from app.vector_db import VectorDB


class FakeEmbedder:
    """Deterministic hash embedding — same text always maps to the same vector."""

    def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    @staticmethod
    def _vec(text: str) -> list[float]:
        return [b / 255.0 for b in hashlib.sha256(text.encode()).digest()[:8]]


def main() -> None:
    chunks = PythonChunker().chunk_file(__file__)
    assert chunks, "chunking produced no chunks for test_pipeline.py itself"

    db = VectorDB(client=QdrantClient(":memory:"))
    db.create_collection("code_chunks", vector_size=8)

    fake = FakeEmbedder()
    db.store_embeddings("code_chunks", chunks, fake.embed_chunks([c.text for c in chunks]))

    retrieved = Retriever(fake, db).retrieve(chunks[0].text, top_k=3)
    assert retrieved, "retrieval returned nothing"
    assert retrieved[0].text == chunks[0].text, (
        f"top hit is '{retrieved[0].text[:40]}...', expected '{chunks[0].text[:40]}...'"
    )
    print(
        f"OK: {len(chunks)} chunks stored; roundtrip hit "
        f"'{retrieved[0].name}' ({retrieved[0].file_path}:{retrieved[0].start_line})"
    )


if __name__ == "__main__":
    main()
