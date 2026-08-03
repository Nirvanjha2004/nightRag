import requests
import json
from qdrant_client import QdrantClient

class VectorDBClass :
    def __init__(self, client: QdrantClient):
        self.client = client

    def create_collection(self, collection_name: str) -> None:
        """Create a collection in the database"""
        if collection_name in self.client.list_collections():
            print(f"Collection {collection_name} already exists")
            return
        print(f"Creating collection {collection_name}")
        self.client.create_collection(
            collection_name=collection_name,
            vector_params={"size": 1536},
            distance={"type": "L2"},
            params={"sharding": {"shards_count": 1}}
        )
        print(f"Collection {collection_name} created")
    def store_embedding(self, collection_name: str, chunk: Chunk , embedding: list[float]) -> None:
        """Store the embedding of a chunk in the database"""
        operation_info = self.client.upsert(
            collection_name=collection_name,
            points=[{
                "id": chunk.id,
                "vector": embedding,
                "payload": chunk.metadata
            }]
        )
        print(f"Stored {len(embedding)} points in collection {collection_name}")
        print(operation_info)

    def query(self, collection_name: str, query: list[float], top_k: int = 5) -> list[dict]:
        """Query the database for the closest embeddings to a query"""
        response = self.client.search(
            collection_name=collection_name,
            query_vector=query,
            top_k=top_k
        )
        return response["result"]
