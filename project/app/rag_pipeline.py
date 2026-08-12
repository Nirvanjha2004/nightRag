"""
rag_pipeline.py — single entry point for the full RAG pipeline.
No embedding, retrieval, prompt-formatting, or generation logic lives here directly —
it only composes retriever.py + prompt_builder.py + generator.py in sequence.

The pipeline is split in two halves:

    prepare(question) -> RagContext   everything up to (not including) the LLM answer
    ask(question)     -> RagResult    prepare + generate, the classic one-shot call

That split exists so a caller can stream the answer (server/ streams tokens as
they arrive) without re-implementing retrieval, and so CorrectiveRagOrchestrator
only has to override the retrieval half.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app import trace
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
class RagContext:
    """Everything the pipeline decided before the answer was generated.

    Carries the corrective-RAG trace so both ask() and a streaming caller can
    report it without knowing which orchestrator produced it.
    """

    question: str
    chunks: list[RetrievedChunk]
    system_prompt: str
    user_prompt: str
    verdict: str | None = None            # "correct" | "ambiguous" | "incorrect"
    rewritten_query: str | None = None    # query used for the corrective round
    corrective_rounds: int = 0            # extra retrieval rounds performed
    refinement: str | None = None         # knowledge-refinement note, if any


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

    @classmethod
    def from_context(cls, context: RagContext, answer: str) -> "RagResult":
        return cls(
            question=context.question,
            answer=answer,
            retrieved_chunks=context.chunks,
            prompt=context.user_prompt,
            verdict=context.verdict,
            rewritten_query=context.rewritten_query,
            corrective_rounds=context.corrective_rounds,
            refinement=context.refinement,
        )


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

    def prepare(self, question: str) -> RagContext:
        """Retrieve + build the prompt. No LLM answer call."""
        trace.emit(trace.RETRIEVE, "start", "Retrieving candidate chunks", top_k=self.top_k)
        chunks = self.retriever.retrieve(question, top_k=self.top_k)
        trace.emit(
            trace.RETRIEVE,
            "done",
            f"Retrieved {len(chunks)} chunk(s)",
            count=len(chunks),
        )

        # build_prompt returns (system_prompt, user_prompt) — send them as
        # separate roles so the model weights the system instructions.
        system_prompt, user_prompt = build_prompt(question, chunks)
        return RagContext(
            question=question,
            chunks=chunks,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def ask(self, question: str) -> RagResult:
        """Full pipeline: retrieve -> build prompt -> generate answer."""
        context = self.prepare(question)
        trace.emit(trace.GENERATE, "start", "Generating answer")
        answer = self.generator.generate(
            context.user_prompt, system_prompt=context.system_prompt
        )
        trace.emit(trace.GENERATE, "done", "Answer complete")
        return RagResult.from_context(context, answer)
