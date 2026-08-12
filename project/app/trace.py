"""
trace.py — opt-in observability for the pipeline stages.

The pipeline modules call ``emit(...)`` at their stage boundaries. By default
that is a no-op: the CLI and run_evals.py keep printing exactly what they
printed before, and nothing pays for tracing it does not consume.

A consumer (the HTTP server's SSE endpoint) installs a sink for the duration of
one request::

    with trace_to(queue.put):
        orchestrator.ask(question)

The sink is held in a ContextVar, so concurrent requests never see each other's
events, and a sink that raises can never break the pipeline (emit swallows).

Threads: a ContextVar set in one thread is NOT visible in a plain
``ThreadPoolExecutor.submit`` worker. That is why emits live at the level of the
component that *owns* the stage (HybridRetriever, not the two retrievers it
fans out to). Install the sink inside the worker thread that runs the pipeline.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

TraceSink = Callable[[dict[str, Any]], Any]

_sink: ContextVar[TraceSink | None] = ContextVar("nightrag_trace_sink", default=None)

# Stage identifiers, so producer and consumer cannot drift apart on spelling.
RETRIEVE = "retrieve"
FUSE = "fuse"
RERANK = "rerank"
EVALUATE = "evaluate"
REWRITE = "rewrite"
CORRECTIVE_RETRIEVE = "corrective_retrieve"
REFINE = "refine"
GENERATE = "generate"


@contextmanager
def trace_to(sink: TraceSink) -> Iterator[None]:
    """Route every ``emit`` in this context (and its callees) to ``sink``."""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def is_tracing() -> bool:
    """True when a sink is installed — lets callers skip expensive detail building."""
    return _sink.get() is not None


def emit(stage: str, status: str = "done", message: str | None = None, **detail: Any) -> None:
    """Record one stage event. No-op (and never raises) when nothing is listening.

    Args:
        stage: one of the module-level stage constants.
        status: "start" | "done" | "skipped" | "error".
        message: short human-readable line for the UI.
        **detail: JSON-serialisable extras (counts, verdicts, timings).
    """
    sink = _sink.get()
    if sink is None:
        return

    event = {"stage": stage, "status": status}
    if message is not None:
        event["message"] = message
    event.update(detail)

    try:
        sink(event)
    except Exception:
        # Tracing is diagnostics. A broken consumer (disconnected client,
        # full queue) must never take down the query it was observing.
        pass
