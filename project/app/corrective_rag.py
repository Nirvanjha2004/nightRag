"""
corrective_rag.py — Corrective RAG (CRAG): grade retrieval, then fix it when it's bad.

Motivation (run 04): the LLM reranker fixed run 03's recall/faithfulness gaps, but
precision is stubborn — a pointwise scorer can still confidently rank irrelevant
noise first (E19 prec 0.0, E17 0.33). CRAG (Yan et al., 2024) attacks exactly that
by making retrieval *self-correcting* instead of trusting a single pass:

    1. RETRIEVE   — the base retriever returns top_k chunks (hybrid RRF + reranker).
    2. EVALUATE   — an LLM retrieval evaluator grades each chunk
                    correct / ambiguous / incorrect for the question.
    3. CORRECT    — by the aggregate verdict:
                      correct   → keep the chunks as-is
                      ambiguous → rewrite the query, retrieve again, merge both sets
                      incorrect → rewrite the query, retrieve fresh, re-evaluate;
                                  if the rewrite round also fails, fall back to the
                                  original set rather than answering from a second
                                  bad retrieval
    4. REFINE     — knowledge refinement: drop chunks graded "incorrect" before
                    building the prompt, so the generator only sees relevant context.

Design rules (mirroring llm_reranker.py):
- Drop-in: CorrectiveRagOrchestrator subclasses RagOrchestrator, so run_evals.py
  and main.py only re-wire, never re-implement.
- Cheap: at most one evaluator call per retrieval round, plus one rewrite call
  when a round is triggered. All calls reuse the shared Generator (and its
  429/413 retry-with-backoff).
- Degrades gracefully: any evaluator/rewrite/retrieve failure (API error,
  unparseable response) falls back to plain RAG on the original chunks — CRAG
  must never make retrieval worse than not running it.
"""

import json
import math
import re

from app import trace
from app.llm_reranker import MAX_CHUNK_CHARS, format_chunk
from app.prompt_builder import build_prompt
from app.rag_pipeline import RagContext, RagOrchestrator
from app.retriever import RetrievedChunk

_CORRECT = "correct"
_AMBIGUOUS = "ambiguous"
_INCORRECT = "incorrect"
_VALID_VERDICTS = frozenset({_CORRECT, _AMBIGUOUS, _INCORRECT})

_EVALUATOR_SYSTEM_PROMPT = """You are a retrieval quality judge for a code search system. Given a question and a numbered list of retrieved code chunks, grade EACH chunk on whether it helps answer the question:

correct — directly helps answer: contains the implementation, definition, default value, error handling, or validation the question asks about
ambiguous — on-topic but incomplete: partially useful, missing key details
incorrect — irrelevant or misleading: does not help answer the question

Judge on SEMANTIC relevance to the question, not keyword overlap — a chunk can mention the right function name and still not answer what is asked. Read each chunk before grading it.

Respond with ONLY a JSON object mapping each chunk number to its verdict, like {"1": "correct", "2": "incorrect", "3": "ambiguous"}. No explanations, no markdown, no other text."""

_REWRITE_SYSTEM_PROMPT = """You are a query rewriter for a code search system that retrieves code chunks. Rewrite the user's question into a concise, symbol-rich search query that maximizes retrieval recall:

- Keep function/class/method names, parameter names and attribute names EXACTLY as written.
- Add likely-relevant technical terms that appear in the question: the function asked about, the error type, the module path.
- Remove conversational filler and rephrase as a search query.
- Do NOT invent APIs that do not appear in the original question.

Respond with ONLY the rewritten question — no quotes, no explanations, no markdown."""


def parse_verdicts(response: str) -> dict[int, str]:
    """Best-effort parse of an evaluator verdict-map response.

    Tries, in order:
      1. JSON objects in the response (also handles ```json fences and prose
         around the object). Keys must be chunk numbers; values must be strings
         matching correct/ambiguous/incorrect (case-insensitive). Unknown
         verdicts are skipped.
      2. "N: correct" / "N = ambiguous" style lines.

    Returns {} when nothing parseable is found — the caller falls back to plain
    RAG on the original ordering.
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
        verdicts = {}
        for key, value in obj.items():
            if isinstance(key, str) and key.isdigit() and isinstance(value, str):
                verdict = value.strip().lower()
                if verdict in _VALID_VERDICTS:
                    verdicts[int(key)] = verdict
        if verdicts:
            return verdicts

    # Fallback: lines/sequences like "1: correct", "2 = incorrect".
    pairs = re.findall(r"(\d+)\s*[:=]\s*(correct|ambiguous|incorrect)", response, re.IGNORECASE)
    return {int(num): verdict.lower() for num, verdict in pairs}


def aggregate_verdict(
    verdicts: dict[int, str],
    total: int,
    correct_ratio: float = 0.6,
) -> str | None:
    """Map per-chunk verdicts onto one retrieval verdict.

        correct    — at least ceil(total * correct_ratio) chunks graded correct
                     (with 5 chunks and the default ratio: 3+). The set is
                     trustworthy, generate directly.
        incorrect  — zero chunks graded correct. The set is noise, correct it.
        ambiguous  — in between: some useful chunks, some not. Refine + widen.

    Returns None when there is nothing to judge (empty retrieval or an empty /
    unparseable verdict map) — the caller falls back to plain RAG.
    """
    if not verdicts or total <= 0:
        return None
    correct = sum(1 for v in verdicts.values() if v == _CORRECT)
    threshold = max(1, math.ceil(total * correct_ratio))
    if correct >= threshold:
        return _CORRECT
    if correct == 0:
        return _INCORRECT
    return _AMBIGUOUS


def refine_chunks(chunks: list[RetrievedChunk], verdicts: dict[int, str]) -> list[RetrievedChunk]:
    """Knowledge refinement: drop chunks graded 'incorrect' from the context.

    Chunks with no verdict (e.g. chunks added by a merged rewrite round) are
    kept. Falls back to the original list if every chunk would be dropped — the
    evaluator may be wrong, and an empty context is worse than a noisy one.
    """
    if not verdicts:
        return list(chunks)
    kept = [c for i, c in enumerate(chunks) if verdicts.get(i + 1, _AMBIGUOUS) != _INCORRECT]
    return kept if kept else list(chunks)


def merge_chunks(*ranked_lists: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Concatenate ranked chunk lists, deduplicating by (file, node, name).

    First occurrence wins, so the original retrieval keeps its rank and chunks
    from a rewrite round are appended — same identity convention as fusion.py.
    """
    seen = set()
    merged: list[RetrievedChunk] = []
    for lst in ranked_lists:
        for chunk in lst:
            key = (chunk.file_path, chunk.node_type, chunk.name)
            if key not in seen:
                seen.add(key)
                merged.append(chunk)
    return merged


class CorrectiveRagOrchestrator(RagOrchestrator):
    """RagOrchestrator with a self-correcting retrieval step.

    Same interface and constructor shape as RagOrchestrator, so it is a drop-in
    replacement in build_orchestrator. The trace of what CRAG decided (verdict,
    rewrite, refinement) rides on the returned RagResult's extra fields.
    """

    def __init__(
        self,
        retriever,
        generator,
        top_k: int = 5,
        correct_ratio: float = 0.6,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
    ):
        super().__init__(retriever=retriever, generator=generator, top_k=top_k)
        self.correct_ratio = correct_ratio
        self.max_chunk_chars = max_chunk_chars

    def prepare(self, question: str) -> RagContext:
        """Retrieve -> evaluate -> correct (if needed) -> refine -> build prompt.

        The corrective round is bounded: at most one query rewrite and one extra
        retrieval. Every failure mode degrades to plain RAG on the original set.
        Inherited ask() turns this context into an answer.
        """
        trace.emit(trace.RETRIEVE, "start", "Retrieving candidate chunks", top_k=self.top_k)
        chunks = self.retriever.retrieve(question, top_k=self.top_k)
        trace.emit(
            trace.RETRIEVE, "done", f"Retrieved {len(chunks)} chunk(s)", count=len(chunks)
        )

        trace.emit(trace.EVALUATE, "start", "Grading retrieval quality")
        verdicts = self._evaluate(question, chunks)
        verdict = aggregate_verdict(verdicts, len(chunks), self.correct_ratio)
        trace.emit(
            trace.EVALUATE,
            "done" if verdict else "skipped",
            f"Verdict: {verdict}" if verdict else "Evaluator gave no usable verdict",
            verdict=verdict,
            graded=len(verdicts),
        )

        rewritten_query: str | None = None
        corrective_rounds = 0
        refinement: str | None = None
        final_chunks = chunks

        if verdict is None:
            # Evaluator failed or nothing to judge — plain RAG on the original set.
            pass
        elif verdict == _CORRECT:
            final_chunks = refine_chunks(chunks, verdicts)
            dropped = len(chunks) - len(final_chunks)
            if dropped:
                refinement = f"knowledge refinement dropped {dropped} irrelevant chunk(s)"
        elif verdict == _AMBIGUOUS:
            rewritten_query = self._rewrite(question)
            if rewritten_query:
                extra = self._corrective_retrieve(rewritten_query)
                if extra is not None:
                    corrective_rounds = 1
                    merged = merge_chunks(chunks, extra)
                    final_chunks = refine_chunks(merged, verdicts)
                    dropped = len(merged) - len(final_chunks)
                    if dropped:
                        refinement = f"knowledge refinement dropped {dropped} irrelevant chunk(s)"
                else:
                    # Corrective retrieval failed — refine the original set, same
                    # as the rewrite-failure path below.
                    final_chunks = refine_chunks(chunks, verdicts)
            else:
                final_chunks = refine_chunks(chunks, verdicts)
        else:  # _INCORRECT
            rewritten_query = self._rewrite(question)
            if rewritten_query:
                second = self._corrective_retrieve(rewritten_query)
                if second is not None:
                    corrective_rounds = 1
                    second_verdicts = self._evaluate(rewritten_query, second)
                    second_verdict = aggregate_verdict(
                        second_verdicts, len(second), self.correct_ratio
                    )
                    if second_verdict is not None and second_verdict != _INCORRECT:
                        verdict = second_verdict
                        final_chunks = refine_chunks(second, second_verdicts)
                        dropped = len(second) - len(final_chunks)
                        if dropped:
                            refinement = f"knowledge refinement dropped {dropped} irrelevant chunk(s)"
                    else:
                        # The corrective round did not fix retrieval (rewrite
                        # re-retrieved a bad set, or the re-evaluation was
                        # unparseable) — answer from the original set rather
                        # than from a second bad one.
                        final_chunks = refine_chunks(chunks, verdicts)
                        refinement = "corrective round failed; fell back to original retrieval"
            else:
                final_chunks = refine_chunks(chunks, verdicts)

        final_chunks = final_chunks[: self.top_k]
        trace.emit(
            trace.REFINE,
            "done",
            refinement or f"Context settled on {len(final_chunks)} chunk(s)",
            count=len(final_chunks),
            refinement=refinement,
        )

        system_prompt, user_prompt = build_prompt(question, final_chunks)
        return RagContext(
            question=question,
            chunks=final_chunks,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            verdict=verdict,
            rewritten_query=rewritten_query,
            corrective_rounds=corrective_rounds,
            refinement=refinement,
        )

    def _evaluate(self, query: str, chunks: list[RetrievedChunk]) -> dict[int, str]:
        """Grade each chunk correct/ambiguous/incorrect; {} on any failure."""
        if not chunks:
            return {}
        numbered = "\n\n".join(
            format_chunk(i, chunk, self.max_chunk_chars)
            for i, chunk in enumerate(chunks, start=1)
        )
        user_prompt = (
            f"Question: {query}\n\nRetrieved chunks:\n{numbered}\n\n"
            "Return the verdict map as JSON now."
        )
        try:
            # 1024 budget, not 256: gpt-oss-120b is a reasoning model — its hidden
            # reasoning can eat a 256-token cap and emit an empty response.
            response = self.generator.generate(
                user_prompt,
                system_prompt=_EVALUATOR_SYSTEM_PROMPT,
                temperature=0.0,  # deterministic grading
                max_tokens=1024,
            )
        except Exception as e:
            print(f"[crag] retrieval evaluation failed ({type(e).__name__}: {e}); using plain RAG")
            return {}
        verdicts = parse_verdicts(response)
        if not verdicts:
            print("[crag] evaluation response unparseable; using plain RAG")
        return verdicts

    def _rewrite(self, query: str) -> str | None:
        """Rewrite the query for a corrective retrieval round; None on failure.

        None when the LLM fails, refuses, or merely echoes the original query —
        a same-query round would re-run the full retrieval for nothing.
        """
        trace.emit(trace.REWRITE, "start", "Rewriting the query for a corrective round")
        try:
            response = self.generator.generate(
                f"Question: {query}\n\nReturn only the rewritten search query now.",
                system_prompt=_REWRITE_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=512,
            )
        except Exception as e:
            print(f"[crag] query rewrite failed ({type(e).__name__}: {e}); using original query")
            trace.emit(trace.REWRITE, "error", f"Rewrite failed ({type(e).__name__}); keeping original query")
            return None
        rewritten = response.strip().strip('"').strip("'").strip()
        # The model occasionally appends stray control bytes (e.g. NUL) — drop
        # anything below printable ASCII so the query stays clean for search.
        rewritten = "".join(ch for ch in rewritten if ord(ch) >= 32 or ch in "\n\t")
        if not rewritten or rewritten.lower() == query.lower():
            trace.emit(trace.REWRITE, "skipped", "Rewrite matched the original query")
            return None
        if rewritten.lower().startswith(("none", "n/a", "i cannot", "i can't")):
            trace.emit(trace.REWRITE, "skipped", "Model declined to rewrite")
            return None
        trace.emit(trace.REWRITE, "done", f"Rewrote as: {rewritten}", query=rewritten)
        return rewritten

    def _corrective_retrieve(self, query: str) -> list[RetrievedChunk] | None:
        """Extra retrieval round for a corrected query; None on failure.

        The base retriever already succeeded once — a failure in the corrective
        round must not kill the query, so it falls back to the original set
        (handled by the caller).
        """
        trace.emit(trace.CORRECTIVE_RETRIEVE, "start", "Re-retrieving with the corrected query")
        try:
            chunks = self.retriever.retrieve(query, top_k=self.top_k)
        except Exception as e:
            print(f"[crag] corrective retrieval failed ({type(e).__name__}: {e}); falling back")
            trace.emit(
                trace.CORRECTIVE_RETRIEVE,
                "error",
                f"Corrective retrieval failed ({type(e).__name__}); falling back",
            )
            return None
        trace.emit(
            trace.CORRECTIVE_RETRIEVE,
            "done",
            f"Corrective round returned {len(chunks)} chunk(s)",
            count=len(chunks),
        )
        return chunks
