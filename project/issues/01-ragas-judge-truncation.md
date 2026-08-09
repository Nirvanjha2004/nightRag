# Issue 01 — RAGAS judge truncation keeps skipping rows

**Date:** 2026-08-09 (first seen run 02, recurring since)
**Status:** OPEN
**Component:** `run_ragas.py` + Ollama judge `qwen2.5:3b`
**Severity:** medium

## Symptom
`run_ragas.py` skips rows mid-eval with:

```
IncompleteOutputException(The output is incomplete due to a max_tokens length limit.)
```

and records them in `skipped_rows.jsonl` (`metric(s) faithfulness returned null`).
The victims rotate every run — run 02: E06/E11; run 03: E12; run 04: E06/E12
(18/20 scored in run 04).

## Where it appeared
Faithfulness metric on code-heavy answers; the 3B judge's unbounded chain-of-thought
blows past the generation cap.

## Root cause (hypothesis)
The failure message says output-side (generation cap), not context-side
(`num_ctx` is already 32768 and `JUDGE_MAX_TOKENS` is already 8192). A fixed
output cap can't fully cure a 3B judge that keeps reasoning on long code answers.

## Fix / workaround
- Not yet fixed. Options on the table: a bigger/stronger judge (7B+ local, or
  Groq `openai/gpt-oss-120b`), or accept ~18/20 scored.
- Impact: the scored set changes between runs, which makes run-to-run RAGAS
  comparisons noisy — always compare on the *identical* rows.

## Related
- journey run 02 / 03 / 04 docs (skips noted in each)
- journey backlog idea: "Upgrade the RAGAS judge (7B+ local or Groq)"
