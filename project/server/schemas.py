"""
schemas.py — the HTTP contract.

These models are the single source of truth for what the API accepts and
returns; the TypeScript types in web/src/lib/api.ts mirror them by hand, so keep
field names in sync when you change something here.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.factory import PipelineConfig
from app.rag_pipeline import RagContext, RagResult
from app.retriever import RetrievedChunk


class PipelineOptions(BaseModel):
    """Per-request pipeline knobs. Every field is optional — omitted ones fall
    back to the server's defaults, so a minimal client can post just a question.
    """

    collection: str | None = None
    model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=25)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    candidate_k: int | None = Field(default=None, ge=1, le=50)
    min_score: float | None = Field(default=None, ge=1, le=5)
    rerank: bool | None = None
    crag: bool | None = None

    def to_config(self, defaults: PipelineConfig) -> PipelineConfig:
        return defaults.merged(**self.model_dump())


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    options: PipelineOptions = Field(default_factory=PipelineOptions)


class ChunkOut(BaseModel):
    text: str
    file_path: str
    node_type: str
    name: str
    start_line: int
    end_line: int
    score: float

    @classmethod
    def of(cls, chunk: RetrievedChunk) -> "ChunkOut":
        return cls(
            text=chunk.text,
            file_path=chunk.file_path,
            node_type=chunk.node_type,
            name=chunk.name,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            score=chunk.score,
        )


class CragTrace(BaseModel):
    """What corrective RAG decided. All-empty when CRAG is disabled."""

    verdict: str | None = None
    rewritten_query: str | None = None
    corrective_rounds: int = 0
    refinement: str | None = None

    @classmethod
    def of(cls, source: RagResult | RagContext) -> "CragTrace":
        return cls(
            verdict=source.verdict,
            rewritten_query=source.rewritten_query,
            corrective_rounds=source.corrective_rounds,
            refinement=source.refinement,
        )


class StageEvent(BaseModel):
    """One pipeline stage boundary, as emitted by app/trace.py."""

    stage: str
    status: Literal["start", "done", "skipped", "error"]
    message: str | None = None
    detail: dict = Field(default_factory=dict)


class AskResponse(BaseModel):
    question: str
    answer: str
    chunks: list[ChunkOut]
    crag: CragTrace
    stages: list[StageEvent]
    config: PipelineConfig
    elapsed_ms: int
    prompt: str


class CollectionOut(BaseModel):
    name: str
    points: int
    vector_size: int | None = None
    indexed: bool = False  # BM25 index already warm in memory


class HealthResponse(BaseModel):
    status: Literal["ready", "setup_required"]
    version: str
    storage: str
    default_model: str
    default_collection: str
    missing_keys: list[str]
    collections: list[CollectionOut]
    defaults: PipelineConfig


class IngestRequest(BaseModel):
    source: Literal["path", "git"]
    value: str = Field(min_length=1, max_length=2000)
    collection: str | None = Field(default=None, max_length=120)


class JobOut(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    source: str
    target: str
    collection: str
    created_at: str
    finished_at: str | None = None
    logs: list[str]
    error: str | None = None
    summary: dict | None = None
