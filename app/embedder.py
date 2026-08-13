import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Embedder:
    """Generate embeddings using the Jina AI Embeddings API."""

    URL = "https://api.jina.ai/v1/embeddings"
    MODEL = "jina-embeddings-v5-text-small"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Retry up to 3 times on transient network/SSL errors and 429/503.
        retry_strategy = Retry(
            total=10,
            backoff_factor=10.0,  # 2s, 4s, 8s
            status_forcelist=frozenset({429, 503}),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=True,
        )
        self._session = requests.Session()
        self._session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _embed(
        self,
        texts: list[str],
        task: str,
    ) -> list[list[float]]:
        """Internal helper for generating embeddings."""

        response = self._session.post(
            self.URL,
            headers=self.headers,
            json={
                "model": self.MODEL,
                "task": task,
                "normalized": True,
                "input": texts,
            },
        )

        if not response.ok:
            print(response.status_code)
            print(response.text)
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
        """Generate embeddings for multiple document chunks in batches."""
        embeddings = []
        BATCH_SIZE = 128
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            embeddings.extend(
                self._embed(
                    texts=batch,
                    task="retrieval.passage",
                )
            )
            print(f"Embedded {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)} chunks")
        return embeddings

    def embed_query(self, query: str) -> list[float]:
        """Generate an embedding for a search query."""

        return self._embed(
            texts=[query],
            task="retrieval.query",
        )[0]