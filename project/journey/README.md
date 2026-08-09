# RAG Improvement Journey — NightRag

This folder records the journey of improving the NightRag RAG pipeline, one run at a time.

Every time we change something and re-run the benchmark, add a new numbered entry
(e.g. `02-hybrid-retrieval-38-50.md`) and update the scoreboard below.

## Scoreboard

| Run | Date | Entry | Score | Δ | What changed |
|-----|------|-------|-------|---|--------------|
| 01 | 2026-08-04 | [01-baseline-30-50.md](01-baseline-30-50.md) | **30/50 (60%)** | — | Baseline — no changes, this is the starting point |
| 02 | 2026-08-06 | [02-ragas-eval-qwen3b.md](02-ragas-eval-qwen3b.md) | RAGAS: recall **0.80** / prec **0.90** / corr **0.70** / faith **0.34** (20Q) | — | First RAGAS quality eval — local Ollama `qwen2.5:3b` judge + Jina embeddings (different metric, not comparable to the X/50 score) |
| 03 | 2026-08-07 | [03-hybrid-retrieval.md](03-hybrid-retrieval.md) | RAGAS: recall **0.84** / prec **0.82** / corr **0.67** / faith **0.60** (20Q) | +0.04 rec, +0.26 faith; −0.07 prec, −0.03 corr | **Hybrid retrieval** — BM25 + dense fused with RRF (idea #4 done); recall win (E05 fixed) but precision noise |
| 04 | 2026-08-09 | [04-llm-reranker.md](04-llm-reranker.md) | RAGAS: recall **0.94** / prec **0.82** / corr **0.70** / faith **0.80** (18/20 scored) | +0.07 rec, +0.13 faith, +0.02 prec, +0.04 corr (same 18 rows) | **LLM reranker** — Groq-scored re-ranking of 10 hybrid candidates → top 5 (idea #5 done); all four metrics up on the identical rows, but precision flat (E19 prec 0.0 new) |

_How to read a row: Score = keyword-hit PASS count / 50 questions (run 01) or RAGAS metric means over the
20-question set (runs 02–04). Δ = change vs previous run._

> ℹ️ **Dataset note:** `benchmarks/evals.jsonl` was trimmed from 50 → 20 questions (E01–E20) in commit
> `1a78cb8` ("Remove outdated eval test cases"). Run 01 was scored on the original 50; runs 02–04 cover
> the current 20 (run 04 scored 18/20 — E06/E12 skipped on judge truncation, see the run doc).

## Pre-tracking history (for context, not official runs)

| Score | What was different |
|-------|--------------------|
| 24/50 | Original run: rate-limit errors (413/429) crashed ~10 questions, hyphen-variant keyword mismatches |
| 26/50 | Embedder retries added; prompt-cap attempted |
| **30/50** | Retries + hyphen normalization fully in place; **official baseline** |

## How the benchmark works

```
benchmarks/evals.jsonl     20 questions about the `rich` codebase (Q + expected_answer + keywords)
run_evals.py               runs each question through the full RAG pipeline
eval_results.jsonl         one row per question: {user_input, response, retrieved_contexts, reference}
SCORE                     printed at the end of each run:  keyword-hit PASS / N questions

Optional quality layer (RAGAS, via local Ollama judge + Jina embeddings):
run_ragas.py               scores eval_results.jsonl → ragas_results.jsonl (context_recall,
                          context_precision, faithfulness, answer_correctness)
```

Run it with:

```bash
python run_evals.py                    # collection code_chunks, top_k 5, model openai/gpt-oss-120b
python run_evals.py --top-k 8          # experiment with retrieval params
```

Offline sanity check (no API keys, no server):

```bash
python test_pipeline.py
```

> ⚠️ `uv run` used to hang on this machine — use `./.venv/Scripts/python.exe run_evals.py` if it still does.
> (Run 03 executed fine with `uv run`.)

## How to record a new run (template)

When a change is made and the pipeline is re-run:

1. Copy the template below into `journey/NN-name-score.md`.
2. Fill in the section, paste the full console output into a code block.
3. Update the scoreboard table above.

```markdown
# Run NN — <short title>  (<score>/50)

Date: YYYY-MM-DD
Command: `python run_evals.py <args>`

## What changed
- ...

## Score
- **X/50 (Y%)** — PASS: <list of ids> / FAIL: <list of ids>
- Δ vs previous run: +N / -N

## Failure analysis (count by bucket)
| Bucket | Count | Ids |
|--------|-------|-----|
| Retrieval gap (right chunk not retrieved) | | |
| Keyword mismatch (answer right, phrasing missed) | | |
| Hallucination / wrong answer | | |
| Error (API / infra) | | |

## Notes / observations
- ...

## Console output
```
<paste output here>
```
```
```

## Improvement ideas backlog (highest impact first)

Prioritized hypotheses to test in future runs — each will get its own journal entry:

| # | Idea | Failure class it targets | Est. impact |
|---|------|--------------------------|-------------|
| 1 | **Split large classes into method-level chunks** (+ prepend class header for context) | retrieval gaps (9/20) | High |
| 2 | **Calibrate keyword scoring** (plurals, verb forms, module qualifiers) | keyword mismatches (10/20) | High — makes the score honest |
| 3 | **Restore the prompt-size cap** (`_MAX_PROMPT_CHARS`/`_truncate` in `app/prompt_builder.py` — currently missing from source) | 413/TPM risk — more relevant now the reranker reads 10 chunks | Medium |
| ~~4~~ | ~~**Hybrid retrieval**: BM25 + dense (reciprocal rank fusion)~~ — **DONE in run 03** ([03-hybrid-retrieval.md](03-hybrid-retrieval.md)) | retrieval gaps | Medium ✅ |
| ~~5~~ | ~~**Reranker** over top-20 → top-5~~ — **DONE in run 04** as an **LLM reranker** ([04-llm-reranker.md](04-llm-reranker.md)): Groq-scored re-ranking of `candidate_k=10` hybrid candidates → top 5 (`app/llm_reranker.py`, on by default) | retrieval gaps + precision | Medium ✅ |
| 6 | **Calibrate the reranker** — `--min-score` threshold + `--candidate-k` sweep; A/B `--no-rerank` | precision (E19 prec 0.0, E17 0.33) | High — next up |
| 7 | **Module-level context chunks** (file header / imports / docstrings) | retrieval gaps | Medium |
| 8 | **Query rewriting** for symbol-heavy questions (e.g. append `class_definition`/`function_definition`) | retrieval gaps | Low–Medium |
| 9 | **Better generation**: higher `max_tokens`, stronger model or higher TPM tier | answer completeness | Medium |
| 10 | **Upgrade the RAGAS judge** (7B+ local or Groq `gpt-oss-120b`) + `max_tokens=4096`; fix deprecated `ragas.metrics` imports | faithfulness metric trustworthiness (see [02-ragas-eval-qwen3b.md](02-ragas-eval-qwen3b.md)) | High |
| 11 | **RRF tuning**: sweep `--rrf-k` (30/60/100), per-retriever top_k (BM25 top-10 → fuse → top-5), BM25 min-score floor | precision regression from run 03 (E13 prec 0.0, E17/E20 dips) | High |
| 12 | **Persist the BM25 index** at ingestion time (pickle next to `qdrant_data`) instead of rebuilding at every process start | startup cost as the corpus grows | Low–Medium |

See [01-baseline-30-50.md](01-baseline-30-50.md), [02-ragas-eval-qwen3b.md](02-ragas-eval-qwen3b.md),
[03-hybrid-retrieval.md](03-hybrid-retrieval.md), and [04-llm-reranker.md](04-llm-reranker.md) for the
analysis behind these.
