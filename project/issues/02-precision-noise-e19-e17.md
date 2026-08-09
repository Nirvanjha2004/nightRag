# Issue 02 — Precision noise: irrelevant chunk ranked #1 (E19 0.0, E17 0.33)

**Date:** 2026-08-09 (first seen run 03, still open in run 04)
**Status:** OPEN
**Component:** retrieval / LLM reranker ordering (`app/llm_reranker.py`)
**Severity:** medium

## Symptom
`context_precision` is the stubborn metric: flat across runs 03→04 (+0.018 on
identical rows) while recall/faithfulness jumped. Per-row smoking guns:
- **E19 prec 0.00** (`Color.parse('rgb(1,2)')` — two components): the reranker
  rated an rgb-wording chunk above the actual arity-check implementation → rank 1.
- **E17 prec 0.33** (`Color.parse('default')` → `ColorType.DEFAULT`): still the
  worst precision row; the reranker didn't fix it.

## Where it appeared
`run_evals.py` on E19 / E17; visible in `ragas_results.jsonl` per-row precision.

## Root cause (hypothesis)
RRF promotes lexically rich but semantically wrong chunks, and the pointwise LLM
scorer can be *confidently wrong* about noise — it re-orders within the 10-chunk
pool but can't add a chunk the pool excluded, and can put keyword-noise first.

## Fix / workaround
- Untested knobs already wired: `--min-score 3` (drop reranker-rated ≤2 chunks
  before the top-k cut), `--candidate-k 20` (bigger pool).
- **Corrective RAG knowledge refinement** (new, run 05) targets exactly this:
  the evaluator grades chunks correct/ambiguous/incorrect and `incorrect` chunks
  are dropped from the prompt — verification pending.
- If CRAG lands, re-check E19/E17 precision specifically.

## Related
- journey run 03 (E13 0.0 fixed by reranker in run 04), run 04 (E19 0.0 new)
- journey backlog ideas: "Calibrate the reranker", "RRF tuning sweep"
