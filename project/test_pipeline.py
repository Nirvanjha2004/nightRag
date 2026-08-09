"""
test_pipeline.py — offline end-to-end check of the RAG wiring.
No Jina key, no Groq key, no Qdrant server needed: a deterministic fake
embedder + in-memory Qdrant prove that chunk -> embed -> store -> retrieve
still work together.

Run: python test_pipeline.py   (from the project root)
"""

import hashlib

from qdrant_client import QdrantClient

from app.chunking import PythonChunker
from app.retriever import Retriever
from app.vector_db import VectorDB


class FakeEmbedder:
    """Deterministic hash embedding — same text always maps to the same vector."""

    def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    @staticmethod
    def _vec(text: str) -> list[float]:
        return [b / 255.0 for b in hashlib.sha256(text.encode()).digest()[:8]]


def main() -> None:
    chunks = PythonChunker().chunk_file(__file__)
    assert chunks, "chunking produced no chunks for test_pipeline.py itself"

    db = VectorDB(client=QdrantClient(":memory:"))
    db.create_collection("code_chunks", vector_size=8)

    fake = FakeEmbedder()
    db.store_embeddings("code_chunks", chunks, fake.embed_chunks([c.text for c in chunks]))

    retrieved = Retriever(fake, db).retrieve(chunks[0].text, top_k=3)
    assert retrieved, "retrieval returned nothing"
    assert retrieved[0].text == chunks[0].text, (
        f"top hit is '{retrieved[0].text[:40]}...', expected '{chunks[0].text[:40]}...'"
    )
    print(
        f"OK: {len(chunks)} chunks stored; roundtrip hit "
        f"'{retrieved[0].name}' ({retrieved[0].file_path}:{retrieved[0].start_line})"
    )


def _check_keyword_score() -> None:
    """Hyphen-mismatch regression: hyphen variants must not cause false FAILs."""
    from run_evals import keyword_score

    # Non-breaking hyphen U+2011 vs keyword with plain hyphen.
    assert keyword_score("it splits at double\u2011width chars", ["double-width"]) == (True, [])
    # Hyphenated form vs keyword with a space.
    assert keyword_score("escapes square\u2011brackets literally", ["square brackets"]) == (True, [])
    # Genuine miss still reported.
    assert keyword_score("raises TypeError", ["TypeError", "ValueError"]) == (False, ["ValueError"])
    print("OK: keyword_score normalizes hyphen variants")


def _check_generator_retries() -> None:
    """Generator retries 429/413 rate-limit errors with backoff; propagates others."""
    from types import SimpleNamespace
    from unittest import mock

    import httpx
    from groq import APIStatusError, RateLimitError
    from app.generator import Generator

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

    def rate_limited(status: int) -> RateLimitError:
        return RateLimitError(
            "rate limit reached",
            response=httpx.Response(status, request=request),
            body={"error": {"type": "tokens", "code": "rate_limit_exceeded"}},
        )

    class FlakyCompletions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise rate_limited(429)
            if self.calls == 2:
                raise rate_limited(413)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    generator = Generator(api_key="test-key", max_retries=5)
    generator.client = SimpleNamespace(chat=SimpleNamespace(completions=FlakyCompletions()))

    with mock.patch("app.generator.time.sleep") as sleep:
        answer = generator.generate("prompt")

    assert answer == "ok", f"expected retried answer, got {answer!r}"
    assert generator.client.chat.completions.calls == 3, (
        f"expected 3 calls after 429+413, got {generator.client.chat.completions.calls}"
    )
    assert sleep.call_count == 2, f"expected 2 backoff sleeps, got {sleep.call_count}"

    # Non-rate-limit errors must propagate immediately, not be retried.
    class BadCompletions:
        def create(self, **kwargs):
            raise APIStatusError(
                "bad request",
                response=httpx.Response(400, request=request),
                body={},
            )

    generator.client = SimpleNamespace(chat=SimpleNamespace(completions=BadCompletions()))
    try:
        generator.generate("prompt")
    except APIStatusError as e:
        assert e.status_code == 400
    else:
        raise AssertionError("expected non-rate-limit APIStatusError to propagate")
    print("OK: Generator retries rate-limit errors with backoff")


def _check_embedder_retries() -> None:
    """Embedder's session mounts retry adapter for POST requests."""
    from app.embedder import Embedder

    embedder = Embedder(api_key="test-key")
    # The session should have a retry adapter mounted on https://
    # (total=10 since commit 1a78cb8 bumped the embedder's retry budget).
    adapter = embedder._session.get_adapter("https://api.jina.ai")
    assert adapter.max_retries.total == 10, "expected 10 retries"
    assert 429 in adapter.max_retries.status_forcelist, "expected 429 retry"
    assert 503 in adapter.max_retries.status_forcelist, "expected 503 retry"
    print("OK: embedder mounts retry adapter for transient errors")


def _check_hybrid_retrieval() -> None:
    """Hybrid retrieval: BM25 + semantic run concurrently, RRF fuses & dedupes.

    Deterministic offline check (fake embedder + in-memory Qdrant):
      - RRF ordering and dedup are pure-function checked with hand-built lists.
      - A token that only BM25 can find still surfaces in the fused top-k,
        proving the hybrid path isn't silently reduced to semantic-only.
    """
    from app.bm25_retriever import BM25Retriever
    from app.fusion import reciprocal_rank_fusion
    from app.hybrid_retriever import HybridRetriever
    from app.retriever import Retriever, RetrievedChunk, chunk_from_payload

    # --- 1. RRF pure check: rank-based ordering + dedup ---
    def mk(name: str, path: str = "a.py") -> RetrievedChunk:
        return RetrievedChunk(
            text=name, file_path=path, node_type="function_definition",
            name=name, start_line=1, end_line=2, score=0.0,
        )

    a, b, c, d = mk("a"), mk("b"), mk("c"), mk("d")
    fused = reciprocal_rank_fusion([[a, b, c], [b, c, d]], rrf_k=60)
    # b: ranks 2+1 = 1/62+1/61;  c: ranks 3+2;  a: rank 1;  d: rank 3.
    assert [x.name for x in fused] == ["b", "c", "a", "d"], (
        f"unexpected RRF order: {[x.name for x in fused]}"
    )
    assert len(fused) == 4, "RRF must merge duplicates, not repeat them"
    # Duplicate across lists must appear once with summed score.
    assert fused[0].score == 1 / 62 + 1 / 61, f"score {fused[0].score}"

    # --- 2. End-to-end: BM25 over the exact chunks stored in Qdrant ---
    chunks = PythonChunker().chunk_file(__file__)
    db = VectorDB(client=QdrantClient(":memory:"))
    db.create_collection("code_chunks", vector_size=8)
    fake = FakeEmbedder()
    db.store_embeddings("code_chunks", chunks, fake.embed_chunks([c.text for c in chunks]))

    # Rebuild BM25 from the same source the app uses: scroll all points.
    points = db.get_all_points("code_chunks")
    assert len(points) == len(chunks), "get_all_points must return every stored chunk"
    bm25_chunks = [chunk_from_payload(p.payload, 0.0) for p in points]
    bm25 = BM25Retriever(bm25_chunks)

    hybrid = HybridRetriever(
        semantic_retriever=Retriever(fake, db),
        bm25_retriever=bm25,
        rrf_k=60,
    )

    # Find a chunk with a distinctive identifier and query with JUST that token.
    # BM25 must surface it; the hash-based fake embedder can't.
    token = "_check_hybrid_retrieval"
    assert any(token in c.text for c in chunks), "test chunk must contain its own name"
    results = hybrid.retrieve(token, top_k=5)
    assert results, "hybrid retrieval returned nothing"
    assert any(token in c.text for c in results), (
        "BM25 signal lost in fusion — hybrid degraded to semantic-only"
    )

    # Fused list must be deduplicated (identity = file_path/node_type/name).
    ids = [(c.file_path, c.node_type, c.name) for c in results]
    assert len(ids) == len(set(ids)), "hybrid results must not contain duplicates"
    # Scores are fused RRF scores, sorted best-first.
    assert all(results[i].score >= results[i + 1].score for i in range(len(results) - 1)), (
        "fused results must be sorted by RRF score"
    )
    print(f"OK: hybrid retrieval fuses BM25 + semantic (RRF), {len(results)} deduped hits")


def _check_prompt_wiring() -> None:
    """build_prompt's (system, user) tuple must reach Groq as separate roles.

    Regression for the 400 'messages.0.content must be a string' — the tuple
    returned by build_prompt used to be passed wholesale as the user content.
    """
    from types import SimpleNamespace

    from app.generator import Generator
    from app.prompt_builder import build_prompt
    from app.rag_pipeline import RagOrchestrator
    from app.retriever import RetrievedChunk

    chunk = RetrievedChunk(
        text="def foo(): pass",
        file_path="a.py",
        node_type="function_definition",
        name="foo",
        start_line=1,
        end_line=1,
        score=0.5,
    )
    system_prompt, user_prompt = build_prompt("What does foo do?", [chunk])

    assert isinstance(system_prompt, str) and "code assistant" in system_prompt
    assert isinstance(user_prompt, str) and "--- CODE CONTEXT ---" in user_prompt
    assert "def foo(): pass" in user_prompt

    class CaptureCompletions:
        def __init__(self) -> None:
            self.messages = None

        def create(self, **kwargs):
            self.messages = kwargs["messages"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    generator = Generator(api_key="test-key")
    generator.client = SimpleNamespace(chat=SimpleNamespace(completions=CaptureCompletions()))

    answer = generator.generate(user_prompt, system_prompt=system_prompt)
    assert answer == "ok"

    messages = generator.client.chat.completions.messages
    assert [m["role"] for m in messages] == ["system", "user"], f"roles: {messages}"
    assert messages[0]["content"] == system_prompt
    assert messages[1]["content"] == user_prompt
    assert all(isinstance(m["content"], str) for m in messages), "content must be strings"

    # The same path run through RagOrchestrator.ask() — the exact place the
    # tuple used to be passed wholesale — must also produce valid messages.
    class StubRetriever:
        def retrieve(self, query: str, top_k: int = 5):
            return [chunk]

    orchestrator = RagOrchestrator(retriever=StubRetriever(), generator=generator, top_k=5)
    result = orchestrator.ask("What does foo do?")
    assert result.prompt == user_prompt

    messages = generator.client.chat.completions.messages
    assert [m["role"] for m in messages] == ["system", "user"], f"roles: {messages}"
    assert all(isinstance(m["content"], str) for m in messages), "ask() sent non-string content"
    print("OK: build_prompt's (system, user) tuple reaches Groq as separate roles")


def _check_eval_rows() -> None:
    """run_evals reads benchmarks/evals.jsonl and stores the dataset schema."""
    from types import SimpleNamespace

    import run_evals
    from app.retriever import RetrievedChunk

    evals = run_evals.load_evals()
    assert len(evals) >= 2, f"expected benchmark entries, got {len(evals)}"

    chunks = [
        RetrievedChunk(
            text="chunk one", file_path="a.py", node_type="function_definition",
            name="f1", start_line=1, end_line=5, score=0.9,
        ),
        RetrievedChunk(
            text="chunk two", file_path="b.py", node_type="class_definition",
            name="C", start_line=10, end_line=20, score=0.8,
        ),
    ]

    class FakeOrchestrator:
        def ask(self, question: str):
            return SimpleNamespace(answer="fake answer", retrieved_chunks=chunks)

    results, passed = run_evals.evaluate(FakeOrchestrator(), evals[:2])
    assert passed == 0  # fake answer won't hit keywords; we only check the schema here

    expected_keys = {"user_input", "response", "retrieved_contexts", "reference"}
    for row, ev in zip(results, evals[:2]):
        assert set(row) == expected_keys, f"row keys {set(row)} != {expected_keys}"
        assert row["user_input"] == ev["question"]
        assert row["reference"] == ev["expected_answer"]
        assert row["response"] == "fake answer"
        assert row["retrieved_contexts"] == ["chunk one", "chunk two"]

    print(f"OK: evaluate() stores dataset rows for {len(results)} benchmark questions")


if __name__ == "__main__":
    main()
    _check_keyword_score()
    _check_generator_retries()
    _check_embedder_retries()
    _check_eval_rows()
    _check_hybrid_retrieval()
    _check_prompt_wiring()
