from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
)

from app.chunking import Chunk


class VectorDB:
    def __init__(self, client: QdrantClient):
        self.client = client

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
    ) -> None:
        """Create a collection if it does not already exist."""

        collections = self.client.get_collections().collections
        collection_names = {collection.name for collection in collections}

        if collection_name in collection_names:
            print(f"Collection '{collection_name}' already exists.")
            return

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(f"Collection '{collection_name}' created.")

    def store_embedding(
        self,
        collection_name: str,
        chunk: Chunk,
        embedding: list[float],
    ) -> None:
        """Store a single chunk embedding."""

        point = PointStruct(
            id=chunk.id,
            vector=embedding,
            payload=chunk.metadata,
        )

        self.client.upsert(
            collection_name=collection_name,
            points=[point],
            wait=True,
        )

        print(f"Stored chunk {chunk.id}")

    def store_embeddings(
        self,
        collection_name: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Store multiple chunk embeddings."""

        if len(chunks) != len(embeddings):
            raise ValueError(
                "Number of chunks and embeddings must be equal."
            )

        points = [
            PointStruct(
                id=chunk.id,
                vector=embedding,
                payload=chunk.metadata,
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        self.client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

        print(f"Stored {len(points)} chunks.")

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ):
        """Search for the nearest embeddings."""

        return self.client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            limit=top_k,
        ).points

    def get_all_points(self, collection_name: str, batch_size: int = 1000):
        """Scroll the entire collection and return all stored points.

        Used by the hybrid retriever to build the BM25 index over exactly the
        same chunks the vector index holds (no separate ingestion path, so the
        two retrievers can never drift apart).
        """
        points = []
        offset = None
        while True:
            batch, offset = self.client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(batch)
            if offset is None:
                return points