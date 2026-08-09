"""
hybrid_retriever.py — combines the semantic (dense) and BM25 (sparse) retrievers.

Retrieval flow per query:
    1. Start the semantic retriever and the BM25 retriever CONCURRENTLY
       (ThreadPoolExecutor — the semantic path is network-bound: Jina embed +
       Qdrant query; BM25 is CPU-bound. Threads overlap the wait instead of
       serializing it.)
    2. Each retriever returns its own top_k ranked list of RetrievedChunk.
    3. reciprocal_rank_fusion merges the two lists by rank (RRF), deduplicating
       chunks that both retrievers returned.
    4. The fused top_k chunks are returned to the caller — the LLM prompt is
       built from exactly this list (see rag_pipeline.py).

Interface is identical to Retriever.retrieve, so HybridRetriever is a drop-in
replacement — RagOrchestrator, run_evals.py and main.py need no other changes.
"""

from concurrent.futures import ThreadPoolExecutor

from app.fusion import reciprocal_rank_fusion
from app.retriever import RetrievedChunk


class HybridRetriever:
    def __init__(
        self,
        semantic_retriever,
        bm25_retriever,
        rrf_k: int = 60,
    ):
        self.semantic_retriever = semantic_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Run semantic + BM25 retrieval concurrently, fuse with RRF, return top_k.

        Flow:
            semantic ──┐                        ┌─► reciprocal_rank_fusion ─► top_k
            bm25     ──┴─► (both run in threads) ┘
        """

        # Step 1+2: launch both retrievers in parallel; each returns top_k.
        with ThreadPoolExecutor(max_workers=2) as pool:
            semantic_future = pool.submit(self.semantic_retriever.retrieve, query, top_k)
            bm25_future = pool.submit(self.bm25_retriever.retrieve, query, top_k)
            semantic_results = semantic_future.result()
            bm25_results = bm25_future.result()

        # Step 3: fuse by rank, deduplicating shared chunks.
        fused = reciprocal_rank_fusion(
            [semantic_results, bm25_results],
            rrf_k=self.rrf_k,
        )

        # Step 4: hand the LLM only the fused top_k.
        return fused[:top_k]
