"""
routes.py — the HTTP surface.

Everything in the pipeline is blocking (network calls to Jina/Groq, a local
Qdrant, CPU-bound BM25), so no handler does that work on the event loop:
one-shot calls go through ``asyncio.to_thread``, and the streaming endpoint runs
the pipeline in a worker thread that pushes events back into an asyncio queue.

Streaming uses Server-Sent Events over POST (rather than the EventSource API,
which is GET-only) — the browser reads it with fetch + a ReadableStream. Each
line is ``data: <json>\\n\\n``; see web/src/lib/stream.ts for the consumer.
"""

import asyncio
import json
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, AsyncIterator, Callable, ContextManager

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import __version__, trace
from app.factory import PipelineConfig
from server.engine import EngineError, RagEngine
from server.jobs import Job, JobRegistry
from server.schemas import (
    AskRequest,
    AskResponse,
    ChunkOut,
    CollectionOut,
    CragTrace,
    HealthResponse,
    IngestRequest,
    JobOut,
    StageEvent,
)
from server.settings import Settings
from server.sources import SourceError, clone_repo, extract_zip, resolve_path

router = APIRouter(prefix="/api")

# Keys that app/trace.py sets on every event; anything else is stage-specific
# detail and rides along in `detail` so the UI can render it generically.
_STAGE_KEYS = frozenset({"stage", "status", "message"})


def get_engine(request: Request) -> RagEngine:
    return request.app.state.engine


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs


def _defaults(settings: Settings) -> PipelineConfig:
    return PipelineConfig(
        collection=settings.default_collection, model=settings.default_model
    )


def _to_stage_event(event: dict) -> StageEvent:
    return StageEvent(
        stage=event.get("stage", "unknown"),
        status=event.get("status", "done"),
        message=event.get("message"),
        detail={k: v for k, v in event.items() if k not in _STAGE_KEYS},
    )


# ---------------------------------------------------------------- health
@router.api_route("/get-health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok"}

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Everything the UI needs to decide between "ready" and a setup screen."""
    settings = get_settings(request)
    engine = get_engine(request)

    try:
        collections = await asyncio.to_thread(engine.describe_collections)
    except Exception as e:
        # Storage that will not open is a setup problem, not a crash — report it
        # as zero collections and let the UI show the missing-keys/setup state.
        print(f"[server] could not read collections: {type(e).__name__}: {e}")
        collections = []

    missing = settings.missing_keys()
    ready = not missing and bool(collections)
    return HealthResponse(
        status="ready" if ready else "setup_required",
        version=__version__,
        storage=engine.storage_label,
        default_model=settings.default_model,
        default_collection=settings.default_collection,
        missing_keys=missing,
        collections=[CollectionOut(**c) for c in collections],
        defaults=_defaults(settings),
    )


# ----------------------------------------------------------- collections


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(request: Request) -> list[CollectionOut]:
    engine = get_engine(request)
    collections = await asyncio.to_thread(engine.describe_collections)
    return [CollectionOut(**c) for c in collections]


@router.delete("/collections/{name}")
async def delete_collection(name: str, request: Request) -> dict:
    engine = get_engine(request)
    try:
        await asyncio.to_thread(engine.drop_collection, name)
    except EngineError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"deleted": name}


# ------------------------------------------------------------------ ask


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, request: Request) -> AskResponse:
    """One-shot ask. Same pipeline as /ask/stream, buffered into one response."""
    engine = get_engine(request)
    config = payload.options.to_config(_defaults(get_settings(request)))

    def run() -> tuple[Any, list[dict], int]:
        events: list[dict] = []
        started = time.perf_counter()
        with trace.trace_to(events.append):
            orchestrator = engine.pipeline(config)
            result = orchestrator.ask(payload.question)
        return result, events, int((time.perf_counter() - started) * 1000)

    try:
        result, events, elapsed_ms = await asyncio.to_thread(run)
    except EngineError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")

    return AskResponse(
        question=result.question,
        answer=result.answer,
        chunks=[ChunkOut.of(c) for c in result.retrieved_chunks],
        crag=CragTrace.of(result),
        stages=[_to_stage_event(e) for e in events],
        config=config,
        elapsed_ms=elapsed_ms,
        prompt=result.prompt,
    )


@router.post("/ask/stream")
async def ask_stream(payload: AskRequest, request: Request) -> StreamingResponse:
    """Stream pipeline stages, then the answer, as Server-Sent Events.

    Event shapes (all JSON on a ``data:`` line):
        {"type":"stage",   "stage":..., "status":..., "message":..., "detail":{}}
        {"type":"context", "chunks":[...], "crag":{...}, "prompt":"..."}
        {"type":"token",   "text":"..."}
        {"type":"done",    "elapsed_ms":123}
        {"type":"error",   "message":"..."}
    """
    engine = get_engine(request)
    config = payload.options.to_config(_defaults(get_settings(request)))
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    FINISHED = object()

    def push(event: Any) -> None:
        # Called from the worker thread — hop back onto the loop thread.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run() -> None:
        started = time.perf_counter()
        try:
            # The sink is installed inside this thread: app/trace.py keeps it in
            # a ContextVar, which does not cross thread boundaries on its own.
            with trace.trace_to(lambda e: push({"type": "stage", **_to_stage_event(e).model_dump()})):
                push({"type": "stage", "stage": "index", "status": "start",
                      "message": "Preparing retrieval indexes", "detail": {}})
                orchestrator = engine.pipeline(config)
                push({"type": "stage", "stage": "index", "status": "done",
                      "message": "Indexes ready", "detail": {}})

                context = orchestrator.prepare(payload.question)
                push({
                    "type": "context",
                    "chunks": [ChunkOut.of(c).model_dump() for c in context.chunks],
                    "crag": CragTrace.of(context).model_dump(),
                    "prompt": context.user_prompt,
                })

                push({"type": "stage", "stage": trace.GENERATE, "status": "start",
                      "message": "Generating answer", "detail": {}})
                for delta in orchestrator.generator.generate_stream(
                    context.user_prompt, system_prompt=context.system_prompt
                ):
                    push({"type": "token", "text": delta})
                push({"type": "stage", "stage": trace.GENERATE, "status": "done",
                      "message": "Answer complete", "detail": {}})

            push({"type": "done", "elapsed_ms": int((time.perf_counter() - started) * 1000)})
        except EngineError as e:
            push({"type": "error", "message": str(e)})
        except Exception as e:
            push({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            push(FINISHED)

    async def events() -> AsyncIterator[str]:
        worker = asyncio.create_task(asyncio.to_thread(run))
        try:
            while True:
                event = await queue.get()
                if event is FINISHED:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            # The client may have walked away mid-answer. The worker cannot be
            # cancelled (it is deep in a blocking API call), so let it finish
            # into a queue nobody reads rather than leaking an unawaited task.
            if not worker.done():
                await worker

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx would otherwise buffer the stream
        },
    )


# --------------------------------------------------------------- ingest


OpenSource = Callable[[], ContextManager[Path]]


def _run_ingest_job(engine: RagEngine, jobs: JobRegistry, job: Job, open_source: OpenSource) -> None:
    """Body of every ingestion job: resolve the source, then ingest it."""
    jobs.start(job)

    def on_progress(step: str, message: str, **detail) -> None:
        jobs.log(job, message)

    try:
        with open_source() as directory:
            jobs.log(job, f"Reading {directory}")
            summary = engine.ingest_path(str(directory), job.collection, on_progress)
        jobs.succeed(job, summary)
    except (SourceError, EngineError) as e:
        jobs.log(job, str(e))
        jobs.fail(job, str(e))
    except Exception as e:
        message = f"{type(e).__name__}: {e}"
        jobs.log(job, message)
        jobs.fail(job, message)


def _spawn_ingest_job(
    engine: RagEngine, jobs: JobRegistry, job: Job, open_source: OpenSource
) -> None:
    """Run a job on its own daemon thread.

    Deliberately not the default executor: an ingestion can run for minutes, and
    parking it in the pool that also serves /ask would let two uploads stall
    every question asked while they run.
    """
    threading.Thread(
        target=_run_ingest_job,
        args=(engine, jobs, job, open_source),
        name=f"nightrag-ingest-{job.id}",
        daemon=True,
    ).start()


@router.post("/ingest", response_model=JobOut, status_code=202)
async def start_ingest(payload: IngestRequest, request: Request) -> JobOut:
    """Kick off an ingestion from a server-side path or a git URL."""
    settings = get_settings(request)
    engine = get_engine(request)
    jobs = get_jobs(request)
    collection = (payload.collection or settings.default_collection).strip()
    if not collection:
        raise HTTPException(status_code=422, detail="Collection name cannot be empty.")

    if payload.source == "path":
        if not settings.allow_local_path:
            raise HTTPException(
                status_code=403,
                detail="Ingesting server-side paths is disabled (NIGHTRAG_ALLOW_LOCAL_PATH=0).",
            )
        try:
            directory = resolve_path(payload.value)
        except SourceError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Already on disk and not ours to delete — hand it over unwrapped.
        def open_source() -> ContextManager[Path]:
            return nullcontext(directory)
    else:
        if not settings.allow_git_clone:
            raise HTTPException(
                status_code=403,
                detail="Cloning repositories is disabled (NIGHTRAG_ALLOW_GIT_CLONE=0).",
            )
        url = payload.value

        def open_source() -> ContextManager[Path]:
            return clone_repo(url)

    job = jobs.create(payload.source, payload.value, collection)
    _spawn_ingest_job(engine, jobs, job, open_source)
    return JobOut(**job.as_dict())


@router.post("/ingest/upload", response_model=JobOut, status_code=202)
async def upload_ingest(
    request: Request,
    file: UploadFile = File(...),
    collection: str = Form(default=""),
) -> JobOut:
    """Kick off an ingestion from an uploaded .zip of a codebase."""
    settings = get_settings(request)
    engine = get_engine(request)
    jobs = get_jobs(request)

    name = file.filename or "upload.zip"
    if not name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip archive.")

    data = await file.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"{name} is larger than the {settings.max_upload_mb} MB upload limit.",
        )

    def open_source() -> ContextManager[Path]:
        return extract_zip(data, name)

    job = jobs.create("upload", name, (collection or settings.default_collection).strip())
    _spawn_ingest_job(engine, jobs, job, open_source)
    return JobOut(**job.as_dict())


@router.get("/ingest/jobs", response_model=list[JobOut])
async def list_jobs(request: Request) -> list[JobOut]:
    return [JobOut(**job.as_dict()) for job in get_jobs(request).list()]


@router.get("/ingest/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, request: Request) -> JobOut:
    job = get_jobs(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id {job_id}.")
    return JobOut(**job.as_dict())
