"""
engine.py — process-wide ownership of the expensive, shared pieces.

Three things must exist exactly once per process, and this class owns all three:

1. The Qdrant client. In embedded mode (``QdrantClient(path=...)``) it takes an
   exclusive lock on the storage directory, so a second client — in this process
   or another — fails. Every request therefore goes through this one client,
   serialised by VectorDB's lock.
2. The BM25 index. Building it scrolls the whole collection; doing that per
   request would make every question O(corpus). It is cached per collection and
   dropped when that collection is re-ingested.
3. The wired orchestrator. Cached per PipelineConfig, so flipping "rerank off"
   in the UI builds one new pipeline and then reuses it.

Everything here is blocking and thread-safe; the FastAPI layer calls it from a
worker thread.
"""

import threading

from qdrant_client import QdrantClient

from app.bm25_retriever import BM25Retriever
from app.factory import PipelineConfig, build_bm25_retriever, build_orchestrator
from app.ingestion import ingest
from app.rag_pipeline import RagOrchestrator
from app.vector_db import VectorDB
from server.settings import Settings


class EngineError(RuntimeError):
    """A problem the user can fix (missing keys, unknown collection)."""


class RagEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self._vector_db: VectorDB | None = None
        self._bm25: dict[str, BM25Retriever] = {}
        self._pipelines: dict[PipelineConfig, RagOrchestrator] = {}

    # ---------- storage ----------

    @property
    def storage_label(self) -> str:
        return self.settings.qdrant_url or f"embedded:{self.settings.qdrant_dir}"

    def vector_db(self) -> VectorDB:
        """The one VectorDB for this process, opened on first use."""
        with self._lock:
            if self._vector_db is None:
                if self.settings.qdrant_url:
                    client = QdrantClient(
                        url=self.settings.qdrant_url,
                        api_key=self.settings.qdrant_api_key or None,
                    )
                else:
                    client = QdrantClient(path=self.settings.qdrant_dir)
                self._vector_db = VectorDB(client=client)
            return self._vector_db

    def close(self) -> None:
        """Release the storage lock so the directory can be reused."""
        with self._lock:
            if self._vector_db is not None:
                try:
                    self._vector_db.client.close()
                except Exception:
                    pass
            self._vector_db = None
            self._bm25.clear()
            self._pipelines.clear()

    # ---------- collections ----------

    def collection_names(self) -> list[str]:
        return self.vector_db().collection_names()

    def describe_collections(self) -> list[dict]:
        """Name + point count + vector size for every collection."""
        db = self.vector_db()
        described = []
        for name in db.collection_names():
            try:
                info = db.client.get_collection(name)
                vector_size = _vector_size(info)
                points = info.points_count if info.points_count is not None else db.count(name)
            except Exception:
                vector_size, points = None, 0
            described.append(
                {
                    "name": name,
                    "points": points or 0,
                    "vector_size": vector_size,
                    "indexed": name in self._bm25,
                }
            )
        return described

    def drop_collection(self, name: str) -> None:
        db = self.vector_db()
        if name not in db.collection_names():
            raise EngineError(f"Collection '{name}' does not exist.")
        db.delete_collection(name)
        self.invalidate(name)

    # ---------- pipeline ----------

    def bm25_for(self, collection: str) -> BM25Retriever:
        """Cached BM25 index for a collection, built on first use."""
        with self._lock:
            cached = self._bm25.get(collection)
        if cached is not None:
            return cached

        # Built outside the engine lock: indexing a large collection takes
        # seconds, and holding the lock would stall unrelated requests. A rare
        # duplicate build under a race is cheaper than that stall.
        built = build_bm25_retriever(self.vector_db(), collection)
        with self._lock:
            return self._bm25.setdefault(collection, built)

    def pipeline(self, config: PipelineConfig) -> RagOrchestrator:
        """A wired orchestrator for this exact config, cached."""
        missing = self.settings.missing_keys()
        if missing:
            raise EngineError(
                "Missing API key(s): " + ", ".join(missing) + ". Add them to .env and restart."
            )
        if config.collection not in self.collection_names():
            raise EngineError(
                f"Collection '{config.collection}' has not been ingested yet. "
                "Add a codebase from the Corpus tab first."
            )

        with self._lock:
            cached = self._pipelines.get(config)
        if cached is not None:
            return cached

        built = build_orchestrator(
            vector_db=self.vector_db(),
            jina_api_key=self.settings.jina_api_key,
            groq_api_key=self.settings.groq_api_key,
            config=config,
            bm25_retriever=self.bm25_for(config.collection),
        )
        with self._lock:
            return self._pipelines.setdefault(config, built)

    def invalidate(self, collection: str) -> None:
        """Forget every cached artefact that reads `collection`.

        Called after ingestion: the BM25 index and any pipeline holding it are
        now stale, and a question answered from a stale index would silently
        miss the code that was just added.
        """
        with self._lock:
            self._bm25.pop(collection, None)
            for config in [c for c in self._pipelines if c.collection == collection]:
                self._pipelines.pop(config, None)

    # ---------- ingestion ----------

    def ingest_path(self, repo_path: str, collection: str, on_progress=None) -> dict:
        """Chunk + embed + store a directory, then invalidate cached indexes."""
        if not self.settings.jina_api_key:
            raise EngineError("Missing API key: jina_api_key. Add it to .env and restart.")
        try:
            return ingest(
                repo_path=repo_path,
                jina_api_key=self.settings.jina_api_key,
                collection_name=collection,
                vector_db=self.vector_db(),
                on_progress=on_progress,
            )
        finally:
            self.invalidate(collection)


def _vector_size(info) -> int | None:
    """Dig the vector dimension out of a Qdrant collection description.

    The shape differs between named-vector and single-vector collections (and
    across client versions), so every failure just reports "unknown" rather than
    breaking the collections list.
    """
    try:
        params = info.config.params.vectors
    except AttributeError:
        return None
    if params is None:
        return None
    size = getattr(params, "size", None)
    if size is not None:
        return size
    if isinstance(params, dict) and params:
        first = next(iter(params.values()))
        return getattr(first, "size", None)
    return None
