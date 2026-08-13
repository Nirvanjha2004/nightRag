# Problems Log — NightRag

This folder is the single place to record **every problem that comes up** while
developing, testing, or running NightRag — retrieval gaps, judge failures,
API/infra hiccups, crashes, tooling annoyances, anything. One file per problem,
numbered in discovery order (`01-slug.md`, `02-slug.md`, …), plus an entry in
the index below.

Why a dedicated folder: the `journey/` folder records *what changed and the
scores*, but the problems behind those numbers deserve their own trail — a
problem log you can mine for the next improvement idea (each entry's "Root
cause" and "Fix / workaround" columns feed straight into the journey backlog).

## Where problems surface (check these first)

| Source | What it looks like |
|--------|--------------------|
| `python run_evals.py` | `ERROR: <Exception>` lines; `FAIL — missing keywords: [...]` rows (may be a keyword mismatch, not a real bug) |
| `python run_ragas.py` | rows skipped → `skipped_rows.jsonl` (usually judge truncation / context too long) |
| Reranker / CRAG traces | `[reranker] scoring failed ...` / `[crag] ... failed ...; using plain RAG` / `corrective round failed; fell back to original retrieval` |
| Console / terminal | `UnicodeEncodeError`, hangs with no progress, `nohup` runs that never finish |
| `test_pipeline.py` | any failed assertion |

## How to log a new problem

1. Copy `TEMPLATE.md` to `NN-slug.md` (next number, short slug of the problem).
2. Fill it in — even a rough symptom + where it appeared is enough; root cause
   and fix can be added later.
3. Add a row to the index table below and move it between Open / Resolved.
4. If it's fixed, flip `Status:` to `RESOLVED` and note the date + fix.

## Open problems

| # | Date | Component | Problem | Link |
|---|------|-----------|---------|------|
| 01 | 2026-08-09 | `run_ragas.py` (judge) | RAGAS judge truncation keeps skipping rows (E06/E12 in run 04) — scored set changes every run | [01-ragas-judge-truncation.md](01-ragas-judge-truncation.md) |
| 02 | 2026-08-09 | retrieval / reranker | Precision stubbornly flat — E19 prec 0.0, E17 0.33 (noise chunk ranked #1) | [02-precision-noise-e19-e17.md](02-precision-noise-e19-e17.md) |

## Resolved problems

| # | Date | Component | Problem | Resolved | Link |
|---|------|-----------|---------|----------|------|
| 03 | 2026-08-09 | `app/llm_reranker.py` | Reasoning model ate the 256-token cap → empty score maps → reranker silently no-op | 2026-08-09 | [03-reasoning-model-empty-scores.md](03-reasoning-model-empty-scores.md) |
| 04 | 2026-08-09 | `run_evals.py` / `main.py` / `run_ragas.py` | Windows console crash on exotic Unicode (U+202F) in model answers | 2026-08-09 | [04-windows-console-unicode-crash.md](04-windows-console-unicode-crash.md) |
| 05 | 2026-08-09 | `app/generator.py` | Uncapped `retry-after` backoff stalled a single eval question for 16+ min | 2026-08-09 | [05-rate-limit-stall.md](05-rate-limit-stall.md) |
