# RAG Improvement Journey — NightRag

This folder records the journey of improving the NightRag RAG pipeline, one run at a time.

Every time we change something and re-run the benchmark, add a new numbered entry
(e.g. `02-hybrid-retrieval-38-50.md`) and update the scoreboard below.

## Scoreboard

| Run | Date | Entry | Score | Δ | What changed |
|-----|------|-------|-------|---|--------------|
| 01 | 2026-08-04 | [01-baseline-30-50.md](01-baseline-30-50.md) | **30/50 (60%)** | — | Baseline — no changes, this is the starting point |

_How to read a row: Score = keyword-hit PASS count / 50 questions. Δ = change vs previous run._

## Pre-tracking history (for context, not official runs)

| Score | What was different |
|-------|--------------------|
| 24/50 | Original run: rate-limit errors (413/429) crashed ~10 questions, hyphen-variant keyword mismatches |
| 26/50 | Embedder retries added; prompt-cap attempted |
| **30/50** | Retries + hyphen normalization fully in place; **official baseline** |

## How the benchmark works

```
benchmarks/evals.jsonl     50 questions about the `rich` codebase (Q + expected_answer + keywords)
run_evals.py               runs each question through the full RAG pipeline
eval_results.jsonl         one row per question: {user_input, response, retrieved_contexts, reference}
SCORE                     printed at the end of each run:  keyword-hit PASS / 50
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

> ⚠️ `uv run` currently hangs on this machine — use the venv interpreter directly:
> `./.venv/Scripts/python.exe run_evals.py`

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
| 3 | **Restore the prompt-size cap** (`_MAX_PROMPT_CHARS`/`_truncate` in `app/prompt_builder.py` — currently missing from source, test_pipeline.py is red) | 413/TPM risk | Medium |
| 4 | **Hybrid retrieval**: BM25 + dense (reciprocal rank fusion) for symbol-name questions | retrieval gaps | Medium |
| 5 | **Reranker** (e.g. Jina reranker) over top-20 → top-5 | retrieval gaps | Medium |
| 6 | **top_k tuning** + min-score threshold | noise + retrieval | Low–Medium |
| 7 | **Module-level context chunks** (file header / imports / docstrings) | retrieval gaps | Medium |
| 8 | **Query rewriting** for symbol-heavy questions (e.g. append `class_definition`/`function_definition`) | retrieval gaps | Low–Medium |
| 9 | **Better generation**: higher `max_tokens`, stronger model or higher TPM tier | answer completeness | Medium |

See [01-baseline-30-50.md](01-baseline-30-50.md) for the full analysis behind these.
