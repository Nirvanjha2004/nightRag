"""
rag_pipeline.py — single entry point for the full RAG pipeline.
No embedding, retrieval, prompt-formatting, or generation logic lives here directly —
it only composes retriever.py + prompt_builder.py + generator.py in sequence.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.retriever import RetrievedChunk
from app.prompt_builder import build_prompt
from app.generator import Generator

if TYPE_CHECKING:
    from app.hybrid_retriever import HybridRetriever
    from app.retriever import Retriever


class RetrieverLike(Protocol):
    """Anything with Retriever.retrieve's signature — semantic or hybrid."""

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]: ...


@dataclass
class RagResult:
    question: str
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    prompt: str  # kept for debugging/tracing — see what was actually sent to the LLM
    # Corrective-RAG trace (all None/0 when the corrective orchestrator is not
    # used) — lets main.py / run_evals.py report what the pipeline decided.
    verdict: str | None = None            # "correct" | "ambiguous" | "incorrect"
    rewritten_query: str | None = None    # query used for the corrective round
    corrective_rounds: int = 0            # extra retrieval rounds performed
    refinement: str | None = None         # knowledge-refinement note, if any


class RagOrchestrator:
    def __init__(
        self,
        retriever: RetrieverLike,
        generator: Generator,
        top_k: int = 5,
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def ask(self, question: str) -> RagResult:
        """Full pipeline: retrieve -> build prompt -> generate answer."""
        chunks = self.retriever.retrieve(question, top_k=self.top_k)
        # build_prompt returns (system_prompt, user_prompt) — send them as
        # separate roles so the model weights the system instructions.
        system_prompt, user_prompt = build_prompt(question, chunks)
        answer = self.generator.generate(user_prompt, system_prompt=system_prompt)
        return RagResult(
            question=question,
            answer=answer,
            retrieved_chunks=chunks,
            prompt=user_prompt,
        )

