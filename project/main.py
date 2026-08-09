"""
main.py — the main orchestrator.

Loads API keys from .env, connects to the local embedded Qdrant store, and runs
the full RAG pipeline (retrieve -> prompt -> generate) against a question.

Usage:
    One-shot question:
        python main.py "Where is the overdraft fee defined?"

    Interactive REPL (type questions, 'exit' to quit):
        python main.py

    Options:
        --collection <name>   Qdrant collection (default: code_chunks)
        --qdrant-dir <dir>    Local Qdrant data dir (default: qdrant_data)
        --top-k <n>           Chunks retrieved per question (default: 5)
        --rrf-k <n>           RRF fusion constant (default: 60)
        --model <model>       Groq model id (default: openai/gpt-oss-120b)
        --candidate-k <n>     Chunks fetched before LLM reranking (default: 10)
        --min-score <x>       Drop reranked chunks rated below x (1-5); unset = keep top_k
        --no-rerank           Skip the LLM reranker (hybrid RRF only)
        --no-crag             Skip corrective RAG (retrieval evaluator + rewrite)

    Corrective RAG (default on): an LLM grades the retrieved chunks
    correct/ambiguous/incorrect; ambiguous/incorrect retrievals trigger a query
    rewrite + re-retrieval, and chunks graded irrelevant are dropped from the
    prompt (knowledge refinement). Pass --no-crag for plain reranked RAG.

    Run ingestion FIRST to build the collection:
        python -m app.ingestion sample_code --local
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient

from app.bm25_retriever import BM25Retriever
from app.config import load_env
from app.embedder import Embedder
from app.generator import Generator
from app.corrective_rag import CorrectiveRagOrchestrator
from app.hybrid_retriever import HybridRetriever
from app.llm_reranker import LLMReranker
from app.rag_pipeline import RagOrchestrator
from app.retriever import Retriever, chunk_from_payload
from app.vector_db import VectorDB

DEFAULT_QDRANT_DIR = "qdrant_data"
DEFAULT_COLLECTION = "code_chunks"
DEFAULT_MODEL = "openai/gpt-oss-120b"


def build_orchestrator(
    qdrant_dir: str = DEFAULT_QDRANT_DIR,
    collection: str = DEFAULT_COLLECTION,
    model: str = DEFAULT_MODEL,
    top_k: int = 5,
    rrf_k: int = 60,
    rerank: bool = True,
    candidate_k: int = 10,
    min_score: float | None = None,
    crag: bool = True,
) -> RagOrchestrator:
    """Wire the full pipeline: .env keys + local Qdrant -> RagOrchestrator.

    By default the hybrid retriever's fused top-k is re-ranked by an LLM
    (LLMReranker): it fetches candidate_k candidates, scores each 1-5 against
    the query, and returns the best top_k. Pass rerank=False for the raw
    hybrid path.

    By default the reranked result is then wrapped in CorrectiveRagOrchestrator:
    an LLM grades the retrieved chunks, triggers a query rewrite + re-retrieval
    when retrieval is ambiguous/incorrect, and drops chunks graded irrelevant
    before generation (knowledge refinement). Pass crag=False for plain
    reranked RAG.
    """
    load_env()

    jina_api_key = os.environ.get("jina_api_key")
    groq_api_key = os.environ.get("groq_api_key")
    if not jina_api_key or not groq_api_key:
        print(
            "Missing API keys in .env — both 'groq_api_key' and 'jina_api_key' are required."
        )
        sys.exit(2)

    vector_db = VectorDB(client=QdrantClient(path=qdrant_dir))

    collection_names = {c.name for c in vector_db.client.get_collections().collections}
    if collection not in collection_names:
        print(f"Collection '{collection}' not found in {qdrant_dir}.")
        print("Run ingestion first:  python -m app.ingestion sample_code --local")
        sys.exit(1)

    semantic_retriever = Retriever(
        embedder=Embedder(api_key=jina_api_key),
        vector_db=vector_db,
        collection_name=collection,
    )

    # Hybrid: build the BM25 index over the exact chunks stored in Qdrant,
    # then run BM25 + semantic retrieval concurrently and fuse with RRF.
    #
    # ponytail: the whole collection is scrolled + re-indexed in memory on
    # every process start — O(chunks) reads at startup, O(chunks) per query
    # to score. Fine for repo-scale corpora. If it ever gets slow, persist the
    # index at ingestion time (e.g. pickle next to qdrant_data) and load it
    # here instead of rebuilding.
    points = vector_db.get_all_points(collection)
    chunks = [chunk_from_payload(p.payload, 0.0) for p in points]
    bm25_retriever = BM25Retriever(chunks)
    print(f"BM25 index built over {len(chunks)} chunks.")

    hybrid = HybridRetriever(
        semantic_retriever=semantic_retriever,
        bm25_retriever=bm25_retriever,
        rrf_k=rrf_k,
    )

    # The generator is shared: it produces the reranker's relevance ratings AND
    # the final answer (its 429/413 retry-with-backoff protects both callers).
    generator = Generator(api_key=groq_api_key, model=model)

    if rerank:
        retriever = LLMReranker(
            base_retriever=hybrid,
            generator=generator,
            candidate_k=candidate_k,
            min_score=min_score,
        )
        print(f"LLM reranker enabled (candidate_k={candidate_k}, min_score={min_score}).")
    else:
        retriever = hybrid

    if crag:
        print("Corrective RAG enabled (retrieval evaluator + query rewrite + knowledge refinement).")
        return CorrectiveRagOrchestrator(retriever=retriever, generator=generator, top_k=top_k)
    return RagOrchestrator(retriever=retriever, generator=generator, top_k=top_k)


def print_answer(result) -> None:
    """Pretty-print a RagResult: the answer plus the chunks it was grounded on."""
    print("\n" + "=" * 70)
    print("ANSWER")
    print("=" * 70)
    print(result.answer)
    print("\n" + "=" * 70)
    print(f"SOURCES (top {len(result.retrieved_chunks)} chunks)")
    print("=" * 70)
    for i, chunk in enumerate(result.retrieved_chunks, start=1):
        print(
            f"  [{i}] {chunk.file_path}  {chunk.node_type} '{chunk.name}'  "
            f"lines {chunk.start_line}-{chunk.end_line}  (score {chunk.score:.4f})"
        )
    if result.verdict:
        trace = f"CRAG: verdict={result.verdict}, corrective rounds={result.corrective_rounds}"
        if result.rewritten_query:
            trace += f", rewritten query={result.rewritten_query!r}"
        if result.refinement:
            trace += f", {result.refinement}"
        print(trace)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and CRASH printing exotic model output
    # (e.g. U+202F narrow no-break space) — replace instead of raising.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Run the RAG pipeline: retrieve from Qdrant, answer via Groq.",
    )
    parser.add_argument("question", nargs="*", help="Optional one-shot question")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-dir", default=DEFAULT_QDRANT_DIR)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--no-crag", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    orchestrator = build_orchestrator(
        qdrant_dir=args.qdrant_dir,
        collection=args.collection,
        model=args.model,
        top_k=args.top_k,
        rrf_k=args.rrf_k,
        rerank=not args.no_rerank,
        candidate_k=args.candidate_k,
        min_score=args.min_score,
        crag=not args.no_crag,
    )

    if args.question:
        print_answer(orchestrator.ask(" ".join(args.question)))
        return 0

    # Interactive REPL
    print("NightRag — ask a question about the ingested code. Type 'exit' to quit.")
    while True:
        try:
            question = input("\nQ> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break
        try:
            print_answer(orchestrator.ask(question))
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
