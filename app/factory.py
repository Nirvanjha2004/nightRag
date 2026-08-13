"""
factory.py — one place that knows how the pipeline is wired.

main.py (CLI), run_evals.py (benchmark) and server/ (HTTP API) all need the same
object graph:

    Embedder ─┐
              ├─► Retriever ─┐
    VectorDB ─┘              ├─► HybridRetriever ─► LLMReranker ─► CorrectiveRagOrchestrator
              BM25Retriever ─┘

Only the *ownership* of the Qdrant client differs: the CLI opens one and exits,
the server keeps one alive for its whole lifetime. So this module takes a
VectorDB it does not own, and leaves the caller in charge of the client.
"""

from dataclasses import dataclass, replace

from app.bm25_retriever import BM25Retriever
from app.corrective_rag import CorrectiveRagOrchestrator
from app.embedder import Embedder
from app.generator import Generator
from app.hybrid_retriever import HybridRetriever
from app.llm_reranker import LLMReranker
from app.rag_pipeline import RagOrchestrator
from app.retriever import Retriever, chunk_from_payload
from app.vector_db import VectorDB

DEFAULT_COLLECTION = "code_chunks"
DEFAULT_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class PipelineConfig:
    """Every knob the CLI flags and the HTTP API expose, in one hashable value.

    Frozen so it can be used as a cache key — the server keeps one built
    pipeline per distinct config instead of rebuilding on every request.
    """

    collection: str = DEFAULT_COLLECTION
    model: str = DEFAULT_MODEL
    top_k: int = 5
    rrf_k: int = 60
    candidate_k: int = 10
    min_score: float | None = None
    rerank: bool = True
    crag: bool = True

    def merged(self, **overrides) -> "PipelineConfig":
        """Copy with only the non-None overrides applied."""
        return replace(self, **{k: v for k, v in overrides.items() if v is not None})


def build_bm25_retriever(vector_db: VectorDB, collection: str) -> BM25Retriever:
    """Build the BM25 index over exactly the chunks stored in `collection`.

    Indexing from Qdrant (rather than re-walking the repo) is what keeps the
    sparse and dense retrievers from ever drifting apart — same chunks, same
    text, one ingestion path.

    ponytail: this is O(chunks) reads and stays in memory. Fine for repo-scale
    corpora; the server builds it once per collection and caches it, the CLI
    rebuilds on every start. If it ever gets slow, persist the index at
    ingestion time and load it here instead.
    """
    points = vector_db.get_all_points(collection)
    chunks = [chunk_from_payload(point.payload, 0.0) for point in points]
    return BM25Retriever(chunks)


def build_orchestrator(
    vector_db: VectorDB,
    jina_api_key: str,
    groq_api_key: str,
    config: PipelineConfig,
    bm25_retriever: BM25Retriever | None = None,
) -> RagOrchestrator:
    """Wire the full pipeline for one config against an already-open VectorDB.

    Layers, outermost last:
      1. hybrid  — BM25 + dense retrieval fused with RRF.
      2. rerank  — an LLM scores candidate_k candidates 1-5, keeps the best
                   top_k (skipped when config.rerank is False).
      3. crag    — an LLM grades the retrieval, rewrites the query and
                   re-retrieves when it is ambiguous/incorrect, and drops chunks
                   graded irrelevant (skipped when config.crag is False).

    Pass a prebuilt `bm25_retriever` to reuse a cached index; otherwise one is
    built from the collection.
    """
    semantic_retriever = Retriever(
        embedder=Embedder(api_key=jina_api_key),
        vector_db=vector_db,
        collection_name=config.collection,
    )

    if bm25_retriever is None:
        bm25_retriever = build_bm25_retriever(vector_db, config.collection)

    retriever = HybridRetriever(
        semantic_retriever=semantic_retriever,
        bm25_retriever=bm25_retriever,
        rrf_k=config.rrf_k,
    )

    # The generator is shared: it produces the reranker's relevance ratings, the
    # CRAG verdicts AND the final answer, so its 429/413 retry-with-backoff
    # protects every caller.
    generator = Generator(api_key=groq_api_key, model=config.model)

    if config.rerank:
        retriever = LLMReranker(
            base_retriever=retriever,
            generator=generator,
            candidate_k=config.candidate_k,
            min_score=config.min_score,
        )

    orchestrator_cls = CorrectiveRagOrchestrator if config.crag else RagOrchestrator
    return orchestrator_cls(
        retriever=retriever, generator=generator, top_k=config.top_k
    )
