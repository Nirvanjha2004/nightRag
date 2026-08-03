import requests
import json

class EmbedderClass :
    """Embedder class for chunking text into embeddings"""
    URL = "https://api.jina.ai/v1/embeddings"
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def embed_chunk(self, chunks: list[str]) -> list[float]:
        """Embed a chunk of text into a vector of floats"""
        data = {
            "model": "jina-embeddings-v5-text-small",
            "task": "retrieval.query",
            "normalized": True,
            "input": chunks
        }
        response = requests.post(self.URL, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()["data"]
        