"""
llm_reranker.py — LLM-based reranking over a broad candidate set.

Why rerank at all: hybrid retrieval (BM25 + dense, RRF-fused) is a recall win,
but RRF is rank-only — it can promote a lexically rich but semantically wrong
chunk into the fused top-5 (run 03: E13 precision 0.0). An LLM relevance judge
fixes exactly that: retrieve a *wider* candidate set, score each candidate's
relevance to the query, keep the best top_k.

Flow per query:
    1. base_retriever.retrieve(query, top_k=candidate_k) — e.g. the hybrid
       retriever with candidate_k=10.
    2. Score the candidates with the LLM in small batches (pointwise 1-5
       relevance scale; JSON score-map response, parsed defensively).
    3. Sort by LLM score (stable — ties keep the original fused rank),
       optionally drop chunks below min_score, return top_k.

Cost: candidate_k=10, batch_size=5 → 2 scoring calls per query, each a few
hundred tokens. The scoring calls reuse the same Generator (and its rate-limit
retries) as the final answer.

Interface is identical to Retriever.retrieve, so LLMReranker is a drop-in
replacement — RagOrchestrator, run_evals.py and main.py need no changes other
than wiring (see main.build_orchestrator).
"""

import json
import re
from dataclasses import replace

from app import trace
from app.retriever import RetrievedChunk

# Neutral score when a chunk's rating is missing/unparseable — lands it in the
# middle of the 1-5 scale instead of silently dropping or boosting it.
_DEFAULT_SCORE = 3.0

_RERANK_SYSTEM_PROMPT = """You are a relevance judge for a code search system. Given a question about a codebase and a numbered list of candidate code chunks, score how relevant each candidate is to the question.

Score meaning:
5 — directly answers the question (the implementation, definition, or setting asked about)
4 — highly relevant; contains most of the information needed to answer
3 — relevant; on-topic but missing key details
2 — marginally related; shares keywords but does not actually help answer
1 — irrelevant; no useful connection to the question

Judge on SEMANTIC relevance to the question, not keyword overlap — a chunk can mention the same function name and still not answer what is asked. Read each candidate before scoring it.

Respond with ONLY a JSON object mapping each candidate number to its score, like {"1": 5, "2": 2}. No explanations, no markdown, no other text."""

# Code chunks can be long (whole classes); relevance judgment doesn't need the
# full body — the header + start of the text is enough. Truncating keeps the
# scoring prompts small (cheap, fast, less TPM pressure on the free tier).
# Shared with app/corrective_rag.py (the CRAG evaluator presents chunks the
# same way), hence public names.
MAX_CHUNK_CHARS = 700


def format_chunk(index: int, chunk: RetrievedChunk, max_chars: int = MAX_CHUNK_CHARS) -> str:
    """One candidate's presentation: identity header + (truncated) code text."""
    text = chunk.text
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n… [truncated]"
    return (
        f"[{index}] {chunk.file_path} "
        f"({chunk.node_type}: {chunk.name}, lines {chunk.start_line}-{chunk.end_line})\n"
        f"```\n{text}\n```"
    )


def parse_scores(response: str) -> dict[int, float]:
    """Best-effort parse of a reranker score-map response.

    Tries, in order:
      1. JSON objects in the response (also handles ```json fences and prose
         around the object). Each brace-delimited span is attempted, shortest
         first, then the full greedy span (covers nested braces). Keys must be
         candidate numbers; values must be numeric (True is rejected — a model
         emitting {"1": true} shouldn't read as a score of 1).
      2. "N: score" / "N = score" style lines.

    Returns {} when nothing parseable is found — the caller falls back to the
    original ordering.
    """
    spans = list(re.findall(r"\{.*?\}", response, re.DOTALL))
    greedy = re.search(r"\{.*\}", response, re.DOTALL)
    if greedy and greedy.group() not in spans:
        spans.append(greedy.group())

    for candidate in spans:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        scores = {}
        for key, value in obj.items():
            if (
                isinstance(key, str) and key.isdigit()
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                scores[int(key)] = float(value)
        if scores:
            return scores

    # Fallback: lines/sequences like "1: 4", "2 = 5", "3: 4.5".
    pairs = re.findall(r"(\d+)\s*[:=]\s*(\d(?:\.\d+)?)", response)
    return {int(num): float(score) for num, score in pairs}


class LLMReranker:
    """Score a broad candidate set with an LLM; return the best top_k.

    Wraps any retriever with the Retriever.retrieve interface (semantic,
    BM25-only, or the hybrid fusion) and re-ranks its output. Drop-in for the
    RagOrchestrator's RetrieverLike protocol.
    """

    def __init__(
        self,
        base_retriever,
        generator,
        candidate_k: int = 10,
        batch_size: int = 5,
        min_score: float | None = None,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
    ):
        self.base_retriever = base_retriever
        self.generator = generator
        self.candidate_k = candidate_k
        self.batch_size = batch_size
        self.min_score = min_score
        self.max_chunk_chars = max_chunk_chars

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Fetch candidate_k candidates, LLM-score them, return the best top_k.

        Chunks are scored in order of original fused rank; the final list is
        sorted by LLM score (stable, so equal scores keep their original rank).
        If min_score is set, chunks rated below it are dropped BEFORE the top_k
        cut — so a query with only 3 genuinely relevant chunks returns 3, not
        5 padded with noise. (min_score only applies when reranking actually
        happens: a candidate list already at or below top_k passes through
        untouched, without burning an LLM call.) Each returned chunk's .score
        is the LLM relevance rating (1-5), replacing the RRF score.
        """
        candidates = self.base_retriever.retrieve(query, top_k=self.candidate_k)

        # Nothing to re-rank: no scoring call needed (and no wasted tokens).
        if len(candidates) <= top_k:
            trace.emit(
                trace.RERANK,
                "skipped",
                f"Only {len(candidates)} candidate(s) — nothing to re-rank",
                count=len(candidates),
            )
            return candidates

        trace.emit(
            trace.RERANK,
            "start",
            f"Scoring {len(candidates)} candidates 1-5 for relevance",
            candidates=len(candidates),
        )
        try:
            scores = self._score_all(query, candidates)
        except Exception as e:
            # The base retriever already succeeded — a scoring failure must not
            # kill the query. Degrade to the base order, same as a parse
            # failure. Real API problems still surface: the final answer call
            # uses the same generator and will raise if the key/endpoint is
            # genuinely broken.
            print(f"[reranker] scoring failed ({type(e).__name__}: {e}); using base order")
            trace.emit(
                trace.RERANK,
                "error",
                f"Scoring failed ({type(e).__name__}); keeping fused order",
            )
            return candidates[:top_k]

        # Total parse failure (e.g. every response was unusable) — don't make
        # retrieval worse than the base retriever: hand back the original order.
        if not scores:
            trace.emit(
                trace.RERANK, "error", "No usable scores returned; keeping fused order"
            )
            return candidates[:top_k]

        # Stable sort by LLM score desc — ties keep the original fused rank.
        scored = [(candidate, scores.get(i + 1, _DEFAULT_SCORE))
                  for i, candidate in enumerate(candidates)]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        dropped = 0
        if self.min_score is not None:
            before = len(scored)
            scored = [pair for pair in scored if pair[1] >= self.min_score]
            dropped = before - len(scored)

        kept = [replace(chunk, score=rating) for chunk, rating in scored[:top_k]]
        message = f"Kept top {len(kept)} by LLM relevance"
        if kept:
            message += f" (best {kept[0].score:g}/5)"
        if dropped:
            message += f"; {dropped} below min score {self.min_score:g}"
        trace.emit(trace.RERANK, "done", message, count=len(kept), dropped=dropped)
        return kept

    def _score_all(self, query: str, candidates: list[RetrievedChunk]) -> dict[int, float]:
        """Score every candidate 1-5 with the LLM, in batches of batch_size.

        Candidates are numbered 1..N across ALL batches (global numbering), so
        a score map never has ambiguous keys. Batches are sent sequentially —
        deliberate: the Generator already retries 429/413 rate limits with
        backoff, and firing concurrent scoring calls would just trip them more.
        """
        scores: dict[int, float] = {}

        for start in range(0, len(candidates), self.batch_size):
            batch = candidates[start:start + self.batch_size]
            numbered = "\n\n".join(
                format_chunk(i, chunk, self.max_chunk_chars)
                for i, chunk in enumerate(batch, start=start + 1)
            )
            user_prompt = (
                f"Question: {query}\n\n"
                f"Candidate chunks:\n{numbered}\n\n"
                "Return the score map as JSON now."
            )
            # 1024 budget, not 256: gpt-oss-120b is a reasoning model — its hidden
            # reasoning can consume a 256-token cap entirely, yielding an EMPTY
            # score map that silently degrades to base order (seen live, 2026-08-09).
            response = self.generator.generate(
                user_prompt,
                system_prompt=_RERANK_SYSTEM_PROMPT,
                temperature=0.0,  # deterministic relevance ratings
                max_tokens=1024,
            )
            scores.update(parse_scores(response))

        return scores
