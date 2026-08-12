"""
jobs.py — background ingestion runs, tracked in memory.

Ingesting a repo takes anywhere from seconds to minutes (chunk → embed → store),
which is far too long for a request/response cycle. So the API starts a job,
returns its id immediately, and the UI polls for the growing log.

In memory is deliberate: a job is only meaningful while the process that owns
the Qdrant directory is alive. Restart the server and the collection persists,
the job history does not.
"""

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Enough log lines to follow a run, few enough that a runaway ingestion cannot
# eat the process's memory.
MAX_LOG_LINES = 400

# Jobs are kept for history in the UI; the oldest are evicted past this.
MAX_JOBS = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    source: str          # "path" | "git" | "upload"
    target: str          # the path / URL / filename the user gave
    collection: str
    status: str = "queued"   # queued | running | succeeded | failed
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    summary: dict | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "source": self.source,
            "target": self.target,
            "collection": self.collection,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "logs": list(self.logs),
            "error": self.error,
            "summary": self.summary,
        }


class JobRegistry:
    """Thread-safe store of ingestion jobs, newest first when listed."""

    def __init__(self, max_jobs: int = MAX_JOBS):
        self._lock = threading.RLock()
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._max_jobs = max_jobs

    def create(self, source: str, target: str, collection: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], source=source, target=target, collection=collection)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self._max_jobs:
                self._jobs.popitem(last=False)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(reversed(self._jobs.values()))

    def log(self, job: Job, line: str) -> None:
        with self._lock:
            job.logs.append(line)
            if len(job.logs) > MAX_LOG_LINES:
                # Drop from the middle-front: the first lines (what was scanned)
                # and the last lines (what just happened) are the useful ones.
                del job.logs[: len(job.logs) - MAX_LOG_LINES]

    def start(self, job: Job) -> None:
        with self._lock:
            job.status = "running"

    def succeed(self, job: Job, summary: dict) -> None:
        with self._lock:
            job.status = "succeeded"
            job.summary = summary
            job.finished_at = _now()

    def fail(self, job: Job, error: str) -> None:
        with self._lock:
            job.status = "failed"
            job.error = error
            job.finished_at = _now()
