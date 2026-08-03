import requests


class Embedder:
    """Generate embeddings using the Jina AI Embeddings API."""

    URL = "https://api.jina.ai/v1/embeddings"
    MODEL = "jina-embeddings-v5-text-small"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _embed(
        self,
        texts: list[str],
        task: str,
    ) -> list[list[float]]:
        """Internal helper for generating embeddings."""

        response = requests.post(
            self.URL,
            headers=self.headers,
            json={
                "model": self.MODEL,
                "task": task,
                "normalized": True,
                "input": texts,
            },
        )

        response.raise_for_status()

        return [
            item["embedding"]
            for item in response.json()["data"]
        ]

    def embed_chunk(self, chunk: str) -> list[float]:
        """Generate an embedding for a single document chunk."""

        return self._embed(
            texts=[chunk],
            task="retrieval.passage",
        )[0]

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple document chunks."""

        return self._embed(
            texts=chunks,
            task="retrieval.passage",
        )

    def embed_query(self, query: str) -> list[float]:
        """Generate an embedding for a search query."""

        return self._embed(
            texts=[query],
            task="retrieval.query",
        )[0]