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
        --model <model>       Groq model id (default: openai/gpt-oss-120b)

    Run ingestion FIRST to build the collection:
        python -m app.ingestion sample_code --local
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient

from app.config import load_env
from app.embedder import Embedder
from app.generator import Generator
from app.rag_pipeline import RagOrchestrator
from app.retriever import Retriever
from app.vector_db import VectorDB

DEFAULT_QDRANT_DIR = "qdrant_data"
DEFAULT_COLLECTION = "code_chunks"
DEFAULT_MODEL = "openai/gpt-oss-120b"


def build_orchestrator(
    qdrant_dir: str = DEFAULT_QDRANT_DIR,
    collection: str = DEFAULT_COLLECTION,
    model: str = DEFAULT_MODEL,
    top_k: int = 5,
) -> RagOrchestrator:
    """Wire the full pipeline: .env keys + local Qdrant -> RagOrchestrator."""
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

    retriever = Retriever(
        embedder=Embedder(api_key=jina_api_key),
        vector_db=vector_db,
        collection_name=collection,
    )
    generator = Generator(api_key=groq_api_key, model=model)

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Run the RAG pipeline: retrieve from Qdrant, answer via Groq.",
    )
    parser.add_argument("question", nargs="*", help="Optional one-shot question")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-dir", default=DEFAULT_QDRANT_DIR)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    orchestrator = build_orchestrator(
        qdrant_dir=args.qdrant_dir,
        collection=args.collection,
        model=args.model,
        top_k=args.top_k,
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
