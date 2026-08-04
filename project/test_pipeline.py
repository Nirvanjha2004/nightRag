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
    adapter = embedder._session.get_adapter("https://api.jina.ai")
    assert adapter.max_retries.total == 3, "expected 3 retries"
    assert 429 in adapter.max_retries.status_forcelist, "expected 429 retry"
    assert 503 in adapter.max_retries.status_forcelist, "expected 503 retry"
    print("OK: embedder mounts retry adapter for transient errors")


def _check_prompt_cap() -> None:
    """Prompt builder truncates chunks so the total fits under the cap."""
    from app.prompt_builder import build_prompt, _MAX_PROMPT_CHARS, _truncate
    from app.retriever import RetrievedChunk

    # _truncate keeps short text, cuts long text with a marker.
    assert _truncate("hello", 100) == "hello"
    truncated = _truncate("a" * 1000, 50)
    assert len(truncated) <= 50 + len("\n# ... (truncated)"), f"truncated length {len(truncated)}"
    assert "(truncated)" in truncated

    # build_prompt with a single huge chunk should truncate it.
    huge_chunk = RetrievedChunk(
        text="x" * 100_000,
        file_path="test.py",
        node_type="function_definition",
        name="foo",
        start_line=1,
        end_line=1000,
        score=0.99,
    )
    prompt = build_prompt("test question", [huge_chunk])
    assert len(prompt) <= _MAX_PROMPT_CHARS + 200, f"prompt length {len(prompt)} exceeds cap"
    assert "(truncated)" in prompt, "expected truncation marker"

    # build_prompt with multiple moderate chunks should also fit.
    medium_chunks = [
        RetrievedChunk(text="hello world", file_path="a.py", node_type="function_definition", name=f"f{i}", start_line=1, end_line=2, score=0.9)
        for i in range(5)
    ]
    prompt = build_prompt("test", medium_chunks)
    assert len(prompt) <= _MAX_PROMPT_CHARS + 200, f"prompt length {len(prompt)} exceeds cap"
    assert "(truncated)" not in prompt, "small chunks should not be truncated"

    print("OK: prompt builder caps chunk text to fit under TPM budget")


if __name__ == "__main__":
    main()
    _check_keyword_score()
    _check_generator_retries()
    _check_embedder_retries()
    _check_prompt_cap()
