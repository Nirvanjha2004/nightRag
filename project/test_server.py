"""
test_server.py — offline end-to-end check of the HTTP layer.

No API keys, no Groq, no Jina, no Qdrant server: a deterministic fake embedder,
an in-memory Qdrant and a scripted generator drive the real routes, so this
verifies the parts that only exist above the pipeline —

    * /api/ask returns the answer, its sources and the stage trace
    * /api/ask/stream emits stage → context → token → done, in that order
    * the corrective-RAG trace survives the trip through JSON
    * ingestion rejects bad input before starting a job
    * unknown /api paths 404 instead of falling through to the SPA

Run: python test_server.py   (from the project root)
"""

import hashlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.bm25_retriever import BM25Retriever
from app.chunking import PythonChunker
from app.corrective_rag import CorrectiveRagOrchestrator
from app.hybrid_retriever import HybridRetriever
from app.llm_reranker import LLMReranker
from app.retriever import Retriever, chunk_from_payload
from app.vector_db import VectorDB
from server.app import create_app
from server.settings import Settings

COLLECTION = "test_chunks"
ANSWER = "The retry lives in `Generator.generate`, which sleeps with backoff on 429."


class FakeEmbedder:
    """Deterministic hash embedding — same text always maps to the same vector."""

    def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    @staticmethod
    def _vec(text: str) -> list[float]:
        return [b / 255.0 for b in hashlib.sha256(text.encode()).digest()[:8]]


class FakeGenerator:
    """Answers every pipeline role from a script, and records what it was asked.

    The reranker, the CRAG evaluator and the answer call all go through one
    Generator in production, so one fake has to play all three — it decides
    which by looking at the system prompt it was handed.
    """

    def __init__(self):
        self.calls: list[str] = []

    def _role(self, system_prompt: str | None) -> str:
        text = (system_prompt or "").lower()
        if "relevance judge" in text:
            return "rerank"
        if "retrieval quality judge" in text:
            return "evaluate"
        if "query rewriter" in text:
            return "rewrite"
        return "answer"

    def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024) -> str:
        role = self._role(system_prompt)
        self.calls.append(role)
        if role == "rerank":
            return json.dumps({str(i): 5 - (i % 3) for i in range(1, 11)})
        if role == "evaluate":
            # Graded ambiguous on purpose: it is the branch that exercises the
            # rewrite + re-retrieve + refine path, so the trace has something
            # interesting in it.
            return json.dumps({"1": "correct", "2": "incorrect", "3": "ambiguous"})
        if role == "rewrite":
            return "Generator.generate retry backoff 429 rate limit"
        return ANSWER

    def generate_stream(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
        self.calls.append("answer_stream")
        for word in ANSWER.split(" "):
            yield word + " "


def build_orchestrator(generator: FakeGenerator) -> CorrectiveRagOrchestrator:
    """The real pipeline, with only the two paid services swapped for fakes."""
    chunks = []
    for path in ["app/generator.py", "app/retriever.py", "app/fusion.py"]:
        chunks.extend(PythonChunker().chunk_file(path))
    assert chunks, "chunking produced nothing — is this being run from the project root?"

    embedder = FakeEmbedder()
    db = VectorDB(client=QdrantClient(":memory:"))
    db.create_collection(COLLECTION, vector_size=8)
    db.store_embeddings(COLLECTION, chunks, embedder.embed_chunks([c.text for c in chunks]))

    semantic = Retriever(embedder=embedder, vector_db=db, collection_name=COLLECTION)
    bm25 = BM25Retriever(
        [chunk_from_payload(p.payload, 0.0) for p in db.get_all_points(COLLECTION)]
    )
    hybrid = HybridRetriever(semantic_retriever=semantic, bm25_retriever=bm25)
    reranked = LLMReranker(base_retriever=hybrid, generator=generator, candidate_k=10)
    orchestrator = CorrectiveRagOrchestrator(retriever=reranked, generator=generator, top_k=5)
    orchestrator.vector_db = db  # kept alive for the engine below
    return orchestrator


def build_client(orchestrator) -> TestClient:
    """A real app whose engine hands back the fake-backed pipeline."""
    app = create_app(
        Settings(
            jina_api_key="test",
            groq_api_key="test",
            default_collection=COLLECTION,
            web_dist=Path("web/dist"),
        )
    )
    engine = app.state.engine
    engine._vector_db = orchestrator.vector_db
    engine.pipeline = lambda config: orchestrator
    return TestClient(app)


def read_events(response) -> list[dict]:
    """Parse an SSE body into the list of JSON payloads it carried."""
    events = []
    for frame in response.text.split("\n\n"):
        payload = "\n".join(
            line[len("data:") :].strip()
            for line in frame.splitlines()
            if line.startswith("data:")
        )
        if payload:
            events.append(json.loads(payload))
    return events


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    generator = FakeGenerator()
    orchestrator = build_orchestrator(generator)

    with build_client(orchestrator) as client:
        # ---------------------------------------------------------- health
        health = client.get("/api/health").json()
        assert health["missing_keys"] == [], health
        assert any(c["name"] == COLLECTION for c in health["collections"]), health
        print("OK: /api/health reports keys configured and the collection present")

        # ------------------------------------------------------------- ask
        response = client.post("/api/ask", json={"question": "How are rate limits retried?"})
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["answer"] == ANSWER, body["answer"]
        assert body["chunks"], "no sources returned"
        assert all(
            {"file_path", "name", "start_line", "end_line", "score"} <= set(chunk)
            for chunk in body["chunks"]
        ), body["chunks"][0]
        print(f"OK: /api/ask answers with {len(body['chunks'])} grounded chunk(s)")

        stages = {stage["stage"] for stage in body["stages"]}
        assert {"retrieve", "fuse", "rerank", "evaluate", "refine", "generate"} <= stages, stages
        print(f"OK: the stage trace survives to the client ({len(body['stages'])} stages)")

        # The UI collapses each stage to its latest event. A stage whose last
        # word was "start" renders as still running forever — which is exactly
        # what happened when the hybrid retriever reported fusion under the
        # RETRIEVE name and a corrective round re-opened it.
        latest = {stage["stage"]: stage["status"] for stage in body["stages"]}
        running = [name for name, status in latest.items() if status == "start"]
        assert not running, f"stages left mid-flight after the answer: {running}"
        print("OK: every stage reaches a terminal status, even after a corrective round")

        assert body["crag"]["verdict"] == "ambiguous", body["crag"]
        assert body["crag"]["corrective_rounds"] == 1, body["crag"]
        assert body["crag"]["rewritten_query"], body["crag"]
        print("OK: the corrective round is reported (verdict, rewrite, round count)")

        assert body["elapsed_ms"] >= 0 and body["prompt"], body["elapsed_ms"]
        assert body["config"]["collection"] == COLLECTION, body["config"]
        print("OK: the response carries the config and prompt actually used")

        # -------------------------------------------------- ask (streamed)
        with client.stream(
            "POST", "/api/ask/stream", json={"question": "How are rate limits retried?"}
        ) as stream:
            assert stream.status_code == 200, stream.status_code
            assert "text/event-stream" in stream.headers["content-type"]
            stream.read()
            events = read_events(stream)

        kinds = [event["type"] for event in events]
        assert "stage" in kinds and "context" in kinds and "token" in kinds, kinds
        assert kinds[-1] == "done", kinds[-3:]
        assert "error" not in kinds, [e for e in events if e["type"] == "error"]
        print(f"OK: /api/ask/stream emits {len(events)} events ending in 'done'")

        streamed = "".join(e["text"] for e in events if e["type"] == "token")
        assert streamed.strip() == ANSWER, streamed
        print("OK: the streamed deltas reassemble into the whole answer")

        context = next(e for e in events if e["type"] == "context")
        assert context["chunks"] and context["crag"]["verdict"] == "ambiguous", context["crag"]
        first_token = kinds.index("token")
        assert kinds.index("context") < first_token, kinds
        print("OK: sources and the CRAG verdict arrive before the first token")

        # --------------------------------------------------------- ingest
        rejected = client.post(
            "/api/ingest", json={"source": "path", "value": "does/not/exist", "collection": "x"}
        )
        assert rejected.status_code == 400, rejected.status_code
        assert "not found" in rejected.json()["error"].lower(), rejected.json()
        print("OK: ingesting a missing path is rejected before a job is created")

        bad_zip = client.post(
            "/api/ingest/upload",
            files={"file": ("notes.txt", b"not a zip", "text/plain")},
            data={"collection": "x"},
        )
        assert bad_zip.status_code == 400, bad_zip.status_code
        print("OK: a non-zip upload is rejected")

        assert client.get("/api/ingest/jobs").json() == [], "a rejected request left a job behind"
        print("OK: rejected ingestions leave no job in the registry")

        # ------------------------------------------------------- routing
        assert client.get("/api/nope").status_code == 404
        print("OK: unknown /api paths 404 instead of returning the SPA shell")

        collections = client.get("/api/collections").json()
        assert any(c["name"] == COLLECTION and c["points"] > 0 for c in collections), collections
        print(f"OK: /api/collections reports {collections[0]['points']} indexed chunks")

    print("\nAll server checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
