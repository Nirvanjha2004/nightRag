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

    # A huge retry-after hint (e.g. a daily reset) must be capped — honoring it
    # verbatim would stall a rate-limited run for hours (seen live: a 16-min
    # single-question hang while the TPM window refills in ~60s).
    from app.generator import _backoff_seconds

    resp = httpx.Response(429, request=request, headers={"retry-after": "3600"})
    limited = RateLimitError("rate limit reached", response=resp, body={})
    assert _backoff_seconds(limited, 0) == 60.0, "retry-after must be capped at _MAX_BACKOFF_SECONDS"
    # Small hints are still honored as-is.
    resp_small = httpx.Response(429, request=request, headers={"retry-after": "3"})
    small = RateLimitError("rate limit reached", response=resp_small, body={})
    assert _backoff_seconds(small, 0) == 3.0

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


def _check_llm_reranker() -> None:
    """LLMReranker: reorders by LLM score, filters below min_score, degrades gracefully.

    Fully offline — a stubbed base retriever and a duck-typed Generator with
    scripted score-map responses stand in for the hybrid retriever and Groq.
    """
    from app.llm_reranker import LLMReranker, parse_scores
    from app.retriever import RetrievedChunk

    # --- 1. score-map parsing: JSON, fenced JSON, line fallback, garbage ---
    assert parse_scores('{"1": 5, "2": 2}') == {1: 5.0, 2: 2.0}
    assert parse_scores('```json\n{"1": 4}\n```') == {1: 4.0}
    assert parse_scores('{"1": 5, "note": "irrelevant"}') == {1: 5.0}, "non-digit keys must be skipped"
    assert parse_scores('{"1": true}') == {}, "boolean JSON values must not read as scores"
    assert parse_scores("Scoring: 1 = 3, 2 = 5") == {1: 3.0, 2: 5.0}
    assert parse_scores("I cannot help with that.") == {}
    print("OK: reranker score-map parsing handles JSON, fences and line fallback")

    def mk(name: str, text: str) -> RetrievedChunk:
        return RetrievedChunk(
            text=text, file_path="a.py", node_type="function_definition",
            name=name, start_line=1, end_line=2, score=0.0,
        )

    chunks = [
        mk("a", "def a(): pass"), mk("b", "def b(): pass"),
        mk("c", "def c(): pass"), mk("d", "def d(): pass"),
    ]

    class StubBase:
        def __init__(self, results):
            self.results = list(results)

        def retrieve(self, query: str, top_k: int = 5):
            return self.results

    class FakeGenerator:
        """Duck-typed Generator: returns scripted responses in order, records calls."""

        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
            self.calls.append((prompt, system_prompt, temperature, max_tokens))
            return self.responses.pop(0)

    # --- 2. reorder by LLM score + attach the rating as .score ---
    fake = FakeGenerator(['{"1": 2, "2": 5}', '{"3": 4, "4": 1}'])
    reranker = LLMReranker(base_retriever=StubBase(chunks), generator=fake, batch_size=2)
    top = reranker.retrieve("question", top_k=2)
    assert [c.name for c in top] == ["b", "c"], f"expected b,c got {[c.name for c in top]}"
    assert top[0].score == 5.0 and top[1].score == 4.0, "LLM score must replace RRF score"
    # Scoring calls: deterministic temperature, system judge prompt, batched numbering.
    assert len(fake.calls) == 2, f"expected 2 scoring batches, got {len(fake.calls)}"
    assert fake.calls[0][2] == 0.0, "reranker must score with temperature 0"
    # Regression (2026-08-09): gpt-oss-120b's hidden reasoning ate a 256-token cap
    # and returned an EMPTY score map (silent no-op reranker). The budget must be
    # big enough that reasoning + scores fit.
    assert fake.calls[0][3] >= 512, "scoring token budget must not truncate reasoning output"
    assert fake.calls[0][1] and "relevance judge" in fake.calls[0][1]
    assert "[1]" in fake.calls[0][0] and "[3]" not in fake.calls[0][0], "batches must be numbered per-batch"
    print("OK: reranker reorders by LLM relevance score")

    # --- 3. min_score filters BEFORE the top-k cut ---
    fake = FakeGenerator(['{"1": 2, "2": 5}', '{"3": 4, "4": 1}'])
    reranker = LLMReranker(
        base_retriever=StubBase(chunks), generator=fake, batch_size=2, min_score=4.0
    )
    top = reranker.retrieve("question", top_k=3)
    assert [c.name for c in top] == ["b", "c"], "chunks below min_score must be dropped"
    print("OK: reranker drops chunks below min_score")

    # --- 4. nothing to rerank → no LLM call at all ---
    fake = FakeGenerator(['{"1": 5}'])
    reranker = LLMReranker(base_retriever=StubBase(chunks[:2]), generator=fake, batch_size=2)
    top = reranker.retrieve("question", top_k=2)
    assert [c.name for c in top] == ["a", "b"], "short base list must pass through untouched"
    assert fake.responses == ['{"1": 5}'], "no scoring call expected when nothing to rerank"
    print("OK: reranker skips the LLM when there is nothing to rerank")

    # --- 5. total parse failure degrades to the original order ---
    fake = FakeGenerator(["I cannot help with that.", "Also no."])
    reranker = LLMReranker(base_retriever=StubBase(chunks), generator=fake, batch_size=2)
    top = reranker.retrieve("question", top_k=3)
    assert [c.name for c in top] == ["a", "b", "c"], "unparseable responses must not hurt retrieval"
    print("OK: reranker falls back to original order on unparseable responses")

    # --- 6. a Generator exception during scoring degrades, not crashes ---
    class BrokenGenerator:
        def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
            raise RuntimeError("scoring API down")

    reranker = LLMReranker(base_retriever=StubBase(chunks), generator=BrokenGenerator(), batch_size=2)
    top = reranker.retrieve("question", top_k=3)
    assert [c.name for c in top] == ["a", "b", "c"], "scoring failure must fall back to base order"
    print("OK: reranker falls back to base order when scoring raises")


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

    expected_keys = {"user_input", "response", "retrieved_contexts", "reference", "crag_verdict"}
    for row, ev in zip(results, evals[:2]):
        assert set(row) == expected_keys, f"row keys {set(row)} != {expected_keys}"
        assert row["user_input"] == ev["question"]
        assert row["reference"] == ev["expected_answer"]
        assert row["response"] == "fake answer"
        assert row["retrieved_contexts"] == ["chunk one", "chunk two"]
        assert row["crag_verdict"] is None  # fake result carries no verdict

    print(f"OK: evaluate() stores dataset rows for {len(results)} benchmark questions")


def _check_corrective_rag() -> None:
    """Corrective RAG: evaluator verdicts drive rewrite + refinement, degrades gracefully.

    Fully offline — a stubbed retriever (per-query results) and a duck-typed
    Generator with scripted responses stand in for Qdrant/Groq. Covers verdict
    parsing, aggregation thresholds, refinement, merge dedup, and every branch
    of the corrective flow (correct / ambiguous / incorrect / failures).
    """
    from app.corrective_rag import (
        CorrectiveRagOrchestrator,
        aggregate_verdict,
        merge_chunks,
        parse_verdicts,
        refine_chunks,
    )
    from app.retriever import RetrievedChunk

    def mk(name: str) -> RetrievedChunk:
        return RetrievedChunk(
            text=f"def {name}(): pass", file_path="a.py", node_type="function_definition",
            name=name, start_line=1, end_line=2, score=0.0,
        )

    # --- 1. verdict parsing: JSON, fenced JSON, line fallback, garbage ---
    assert parse_verdicts('{"1": "correct", "2": "incorrect"}') == {1: "correct", 2: "incorrect"}
    assert parse_verdicts('```json\n{"1": "Ambiguous"}\n```') == {1: "ambiguous"}
    assert parse_verdicts("1: correct\n2 = incorrect") == {1: "correct", 2: "incorrect"}
    assert parse_verdicts('{"1": "maybe"}') == {}, "unknown verdicts must be dropped"
    assert parse_verdicts("no idea") == {}
    print("OK: CRAG verdict parsing handles JSON, fences and line fallback")

    # --- 2. aggregation thresholds (top_k=5 -> correct needs >= 3) ---
    assert aggregate_verdict({1: "correct", 2: "correct", 3: "correct", 4: "correct", 5: "correct"}, 5) == "correct"
    assert aggregate_verdict({1: "correct", 2: "correct", 3: "correct", 4: "incorrect", 5: "incorrect"}, 5) == "correct"
    assert aggregate_verdict({1: "correct", 2: "correct", 3: "incorrect", 4: "incorrect", 5: "incorrect"}, 5) == "ambiguous"
    assert aggregate_verdict({1: "incorrect", 2: "incorrect", 3: "ambiguous", 4: "incorrect", 5: "ambiguous"}, 5) == "incorrect"
    assert aggregate_verdict({}, 5) is None
    print("OK: CRAG aggregates per-chunk verdicts into correct/ambiguous/incorrect")

    # --- 3. knowledge refinement + merge dedup ---
    a, b, c, d = mk("a"), mk("b"), mk("c"), mk("d")
    kept = refine_chunks([a, b, c, d], {1: "correct", 2: "incorrect", 3: "ambiguous"})
    assert [x.name for x in kept] == ["a", "c", "d"], "incorrect chunks must be dropped"
    assert refine_chunks([a], {1: "incorrect"}) == [a], "dropping everything falls back to original"
    merged = merge_chunks([a, b], [b, c])
    assert [x.name for x in merged] == ["a", "b", "c"], "merge must dedupe by identity"
    print("OK: CRAG knowledge refinement drops irrelevant chunks; merge dedupes")

    class StubRetriever:
        """Returns the plan's chunks per query, recording every retrieve call."""

        def __init__(self, plan):
            self.plan = plan
            self.calls = []

        def retrieve(self, query: str, top_k: int = 5):
            self.calls.append(query)
            return self.plan[query]

    class ScriptedGenerator:
        """Duck-typed Generator: returns scripted responses in order, records calls."""

        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
            self.calls.append(system_prompt)
            return self.responses.pop(0)

    # --- 4. 'correct' verdict: single retrieval round, no rewrite ---
    chunks = [mk("parse"), mk("color"), mk("rgb"), mk("none"), mk("on")]
    retriever = StubRetriever({"q": chunks})
    gen = ScriptedGenerator([
        '{"1": "correct", "2": "correct", "3": "correct", "4": "correct", "5": "correct"}',
        "the answer",
    ])
    orch = CorrectiveRagOrchestrator(retriever=retriever, generator=gen, top_k=5)
    result = orch.ask("q")
    assert result.verdict == "correct" and result.corrective_rounds == 0
    assert result.rewritten_query is None
    assert retriever.calls == ["q"], "correct retrieval must not trigger a rewrite round"
    assert len(result.retrieved_chunks) == 5
    assert result.answer == "the answer"
    print("OK: CRAG generates directly when retrieval is graded correct")

    # --- 5. 'incorrect' verdict: rewrite + fresh retrieval + re-evaluate ---
    bad = [mk("x"), mk("y"), mk("z"), mk("w"), mk("v")]
    good = [mk("p1"), mk("p2"), mk("p3"), mk("p4"), mk("p5")]
    retriever = StubRetriever({"q": bad, "rewritten q": good})
    gen = ScriptedGenerator([
        '{"1": "incorrect", "2": "incorrect", "3": "incorrect", "4": "incorrect", "5": "incorrect"}',
        "rewritten q",
        '{"1": "correct", "2": "correct", "3": "correct", "4": "correct", "5": "correct"}',
        "the answer",
    ])
    orch = CorrectiveRagOrchestrator(retriever=retriever, generator=gen, top_k=5)
    result = orch.ask("q")
    assert result.verdict == "correct", "verdict must reflect the corrected round"
    assert result.corrective_rounds == 1
    assert result.rewritten_query == "rewritten q"
    assert retriever.calls == ["q", "rewritten q"]
    assert [c.name for c in result.retrieved_chunks] == [c.name for c in good]
    print("OK: CRAG rewrites + re-retrieves when retrieval is graded incorrect")

    # --- 6. 'ambiguous' verdict: rewrite + merge + refine ---
    orig = [mk("parse"), mk("noise"), mk("rgb"), mk("none"), mk("on")]  # parse correct, noise incorrect
    extra = [mk("impl"), mk("color"), mk("rgb2"), mk("none2"), mk("on2")]
    retriever = StubRetriever({"q": orig, "rewritten q": extra})
    gen = ScriptedGenerator([
        '{"1": "correct", "2": "incorrect", "3": "ambiguous", "4": "ambiguous", "5": "ambiguous"}',
        "rewritten q",
        "the answer",
    ])
    orch = CorrectiveRagOrchestrator(retriever=retriever, generator=gen, top_k=5)
    result = orch.ask("q")
    assert result.verdict == "ambiguous"
    assert result.corrective_rounds == 1
    names = [c.name for c in result.retrieved_chunks]
    assert "noise" not in names, "incorrect chunk must be dropped by refinement"
    assert names[0] == "parse", "correct original chunk keeps its rank"
    assert "impl" in names, "rewrite-round chunks must be merged in"
    assert result.refinement and "dropped" in result.refinement
    print("OK: CRAG merges + refines on ambiguous retrieval")

    # --- 7. rewrite round also fails: fall back to the original chunks ---
    bad = [mk("x"), mk("y"), mk("z"), mk("w"), mk("v")]
    also_bad = [mk("x2"), mk("y2"), mk("z2"), mk("w2"), mk("v2")]
    retriever = StubRetriever({"q": bad, "rewritten q": also_bad})
    gen = ScriptedGenerator([
        '{"1": "incorrect", "2": "incorrect", "3": "incorrect", "4": "incorrect", "5": "incorrect"}',
        "rewritten q",
        '{"1": "incorrect", "2": "incorrect", "3": "incorrect", "4": "incorrect", "5": "incorrect"}',
        "the answer",
    ])
    orch = CorrectiveRagOrchestrator(retriever=retriever, generator=gen, top_k=5)
    result = orch.ask("q")
    assert result.verdict == "incorrect"
    assert [c.name for c in result.retrieved_chunks] == [c.name for c in bad]
    assert result.refinement and "fell back" in result.refinement
    print("OK: CRAG falls back to original retrieval when the rewrite round fails")

    # --- 8. evaluator API failure degrades to plain RAG, never crashes ---
    chunks = [mk("a"), mk("b"), mk("c"), mk("d"), mk("e")]
    retriever = StubRetriever({"q": chunks})

    class BrokenEvalGenerator:
        def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
            if "verdict map" in prompt:
                raise RuntimeError("evaluator down")
            return "the answer"

    orch = CorrectiveRagOrchestrator(retriever=retriever, generator=BrokenEvalGenerator(), top_k=5)
    result = orch.ask("q")
    assert result.verdict is None
    assert len(result.retrieved_chunks) == 5, "evaluator failure must keep original chunks"
    assert result.answer == "the answer"
    print("OK: CRAG degrades to plain RAG when the evaluator raises")

    # --- 9. rewrite failure: ambiguous verdict still refines, no extra round ---
    class RewriteFailsGenerator:
        def __init__(self, eval_response, answer):
            self.eval_response = eval_response
            self.answer = answer

        def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1024):
            if system_prompt and "rewriter" in system_prompt:
                raise RuntimeError("rewrite API down")
            if "verdict map" in prompt:
                return self.eval_response
            return self.answer

    retriever = StubRetriever({"q": orig})
    orch = CorrectiveRagOrchestrator(
        retriever=retriever,
        generator=RewriteFailsGenerator(
            '{"1": "correct", "2": "incorrect", "3": "ambiguous", "4": "ambiguous", "5": "ambiguous"}',
            "the answer",
        ),
        top_k=5,
    )
    result = orch.ask("q")
    assert result.corrective_rounds == 0
    assert result.rewritten_query is None
    assert "noise" not in [c.name for c in result.retrieved_chunks]
    assert result.answer == "the answer"
    print("OK: CRAG still refines (no rewrite round) when the rewriter raises")


if __name__ == "__main__":
    main()
    _check_keyword_score()
    _check_generator_retries()
    _check_embedder_retries()
    _check_eval_rows()
    _check_hybrid_retrieval()
    _check_llm_reranker()
    _check_prompt_wiring()
    _check_corrective_rag()
