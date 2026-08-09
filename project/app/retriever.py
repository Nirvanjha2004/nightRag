"""
retriever.py — thin composition layer. No embedding logic, no Qdrant logic here,
just wires Embedder + VectorDB together to go from a plain-text query to ranked chunks.
"""

from dataclasses import dataclass

from app.embedder import Embedder
from app.vector_db import VectorDB


@dataclass
class RetrievedChunk:
    text: str
    file_path: str
    node_type: str
    name: str
    start_line: int
    end_line: int
    score: float


class Retriever:
    def __init__(self, embedder: Embedder, vector_db: VectorDB, collection_name: str = "code_chunks"):
        self.embedder = embedder
        self.vector_db = vector_db
        self.collection_name = collection_name

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Embed the query and return the top_k most similar chunks."""

        query_embedding = self.embedder.embed_query(query)

        results = self.vector_db.query(
            collection_name=self.collection_name,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        return [chunk_from_payload(point.payload, point.score) for point in results]


def chunk_from_payload(payload: dict, score: float) -> RetrievedChunk:
    """Build a RetrievedChunk from a Qdrant point payload + score.

    Shared by the semantic Retriever and the BM25 retriever so both produce
    the same chunk shape — the hybrid retriever can then fuse the two lists.
    """
    return RetrievedChunk(
        text=payload["text"],
        file_path=payload["file_path"],
        node_type=payload["node_type"],
        name=payload["name"],
        start_line=payload["start_line"],
        end_line=payload["end_line"],
        score=score,
    )
