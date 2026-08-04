"""
rag_pipeline.py — single entry point for the full RAG pipeline.
No embedding, retrieval, prompt-formatting, or generation logic lives here directly —
it only composes retriever.py + prompt_builder.py + generator.py in sequence.
"""

from dataclasses import dataclass

from app.retriever import Retriever, RetrievedChunk
from app.prompt_builder import build_prompt
from app.generator import Generator


@dataclass
class RagResult:
    question: str
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    prompt: str  # kept for debugging/tracing — see what was actually sent to the LLM


class RagOrchestrator:
    def __init__(self, retriever: Retriever, generator: Generator, top_k: int = 5):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def ask(self, question: str) -> RagResult:
        """Full pipeline: retrieve -> build prompt -> generate answer."""
        chunks = self.retriever.retrieve(question, top_k=self.top_k)
        prompt = build_prompt(question, chunks)
        answer = self.generator.generate(prompt)
        return RagResult(
            question=question,
            answer=answer,
            retrieved_chunks=chunks,
            prompt=prompt,
        )

