# Issue 03 — Reasoning model ate the 256-token cap → reranker silently no-op

**Date:** 2026-08-09
**Status:** RESOLVED (2026-08-09)
**Component:** `app/llm_reranker.py` (also `app/corrective_rag.py`)
**Severity:** high (silent degradation)

## Symptom
Retrieved chunk `.score` values were RRF-scale (~0.016–0.03) instead of LLM
1–5 ratings. The reranker produced **no error** — it silently returned base
order. No `[reranker] scoring failed` message appeared.

## Where it appeared
`python main.py "Text.append(...)"` and the first full `run_evals.py` attempt.
Debug probe showed `finish_reason: length` with `content: ''` on real-chunk
prompts, while short dummy prompts worked.

## Root cause
`openai/gpt-oss-120b` is a **reasoning model** (`completion_tokens_details.reasoning_tokens`
visible in usage). Its hidden reasoning consumed the whole `max_tokens=256`
budget on non-trivial prompts → empty `content` → `parse_scores('')` → `{}` →
silent fallback to base order. Short prompts fit in 256; real 5-chunk prompts
did not (3.7k-char prompt needed ~78+ tokens of reasoning + scores, and complex
grading scaled past the cap).

## Fix / workaround
Bumped scoring token budgets: reranker + CRAG evaluator `max_tokens` 256 → 1024,
CRAG rewrite 128 → 512. Verified: at 1024 the model returns full score maps
(`{"1": 5, "2": 2, ...}`), at 256 it returns empty.

## Related
- `test_pipeline.py` regression guard: asserts scoring calls use `max_tokens >= 512`
- Note: this class of bug can silently regress if the model's reasoning behavior
  changes again — the token budget, not the prompt, is the lever.
