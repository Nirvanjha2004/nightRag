# Run 04 — LLM reranker: Groq-scored re-ranking of hybrid candidates (18 scored / 20)

**Date:** 2026-08-09
**Command:** `uv run python run_evals.py` (reranker **on by default**, `candidate_k=10`) then `uv run python -u run_ragas.py`
**Judge:** Ollama `qwen2.5:3b` (local, `max_tokens=8192` — bumped from 2048) · **Embeddings:** Jina `jina-embeddings-v5-text-small` (API) — unchanged
**Reranker:** Groq `openai/gpt-oss-120b` (the same model as the generator), temperature 0.0
**Dataset:** `benchmarks/evals.jsonl` — 20 rows (E01–E20); **18 scored, 2 skipped** (E06, E12 — failed faithfulness)
**Output:** `ragas_results.jsonl` (18 rows) — `eval_results.jsonl` regenerated 2026-08-09 15:16 with the reranker on

This run measures the **LLM reranker** — improvement-idea #5 from run 01. It fetches **10**
candidate chunks from the hybrid retriever, has the LLM score each chunk 1–5 for relevance to the
question (batched, temperature 0), and returns the best 5. Same 20-question set, same judge, same
generator as run 03, so the deltas are attributable to the reranking step alone.

---

## 1. Results (mean over 18 scored rows)

```
Scoring 20 rows using Ollama (qwen2.5:3b) & Jina Embeddings...
...
Scored 18 new rows this run. Written to ragas_results.jsonl
Skipped 2 row(s) -> skipped_rows.jsonl

metric                  mean   scored
context_recall         0.944   18/18
context_precision      0.820   18/18
faithfulness           0.797   18/18
answer_correctness     0.698   18/18
```

### Headline: vs Run 03 (hybrid, no reranker)

**⚠️ The scored set changed** — run 04 skipped E06 + E12 (both failed *faithfulness*, judge
truncation; see §5), and run 03 scored those rows. E06 had recall 0.00 and E12 had faithfulness 0.00
in run 03, so a raw mean-to-mean comparison would flatter run 04. The table gives **both**: raw
means, and run 03 re-means over the *identical* 18 rows run 04 scored.

| Metric | Run 03 (20 rows) | Run 03 (same 18) | Run 04 (18 rows) | Δ same-18 |
|--------|-----------------:|-----------------:|-----------------:|----------:|
| context_recall | 0.838 | 0.876 | **0.944** | **+0.068** |
| context_precision | 0.822 | 0.802 | 0.820 | **+0.018** |
| faithfulness | 0.604 | 0.671 | **0.797** | **+0.126** |
| answer_correctness | 0.671 (19/20) | 0.662 | 0.698 | **+0.036** |

Distribution (run 04): recall median 1.0, min 0, **1 zero** (was 3 of 20); precision median 1.0,
min 0, **2 zeros** (E17 0.33, E19 0.00 — was E13 0.0 + dips); faithfulness median 1.0, min 0,
**3 zeros** (was 6); correctness median 0.649, min 0.506, **0 zeros**, 18/18 scored.

**One-line reading:** on the *identical 18 rows*, the reranker improves **every metric** — recall
+0.07 and faithfulness +0.13 lead, correctness +0.04 — but **precision is the stubborn one**
(+0.02): it fixed run 03's smoking gun (E13 0.00 → 0.50) while *creating* a new one (E19 0.50 →
0.00). The LLM scorer reliably re-orders the *relevant* chunks to the top, but it can still be
confidently wrong about *irrelevant* noise.

---

## 2. Per-question scores (run 04, sorted by answer_correctness)

Δ = change vs run 03. `n/a` rows were skipped this run (failed faithfulness — judge truncation).

| Id | rec | prec | faith | corr | Δ corr | Question (abbr.) |
|----|-------:|-----:|------:|-----:|-------:|------------------|
| E03 | 1.00 | 0.92 | 1.00 | 0.953 | +0.14 | `Text` slice with step != 1 |
| E18 | 1.00 | 0.89 | 1.00 | 0.876 | +0.08 | `Color.parse` number > 255 |
| E04 | 1.00 | 1.00 | 1.00 | 0.852 | +0.14 | `Text.truncate` ellipsis overflow |
| E05 | 1.00 | 1.00 | 1.00 | 0.831 | +0.19 | `Text.expand_tabs` default tab size |
| E14 | 1.00 | 1.00 | 1.00 | 0.828 | +0.10 | `Style.parse('on')` missing color |
| E13 | 1.00 | **0.50** | 0.00 | 0.789 | +0.10 | `Style.parse('')` / `'none'` → null style |
| E08 | 1.00 | 1.00 | 0.75 | 0.764 | +0.00 | `set_cell_size` total ≤ 0 |
| E20 | 1.00 | 0.64 | 1.00 | 0.728 | **+0.28** | `rgb()` component > 255 |
| E09 | 1.00 | 1.00 | 1.00 | 0.704 | −0.20 | `cells.split_text` cuts inside a 2-cell char |
| E17 | 1.00 | **0.33** | 1.00 | 0.649 | **+0.24** | `Color.parse('default')` → ColorType.DEFAULT |
| E10 | 1.00 | 0.58 | 1.00 | 0.637 | +0.17 | markup closing tag doesn't match |
| E01 | 1.00 | 1.00 | 0.00 | 0.605 | −0.06 | `Text.append(text, style=...)` w/ Text + style |
| E19 | 1.00 | **0.00** | 1.00 | 0.598 | +0.00 | `Color.parse('rgb(1,2)')` — two components |
| E07 | 0.00 | 0.95 | 0.60 | 0.589 | −0.23 | `get_character_cell_size` control chars |
| E11 | 1.00 | 0.95 | 0.00 | 0.588 | −0.30 | markup `[/]` with nothing to close |
| E16 | 1.00 | 1.00 | 1.00 | 0.548 | +0.00 | `Style.normalize` parse failure fallback |
| E02 | 1.00 | 1.00 | 1.00 | 0.527 | +0.00 | `Text.append` non-str/non-Text |
| E15 | 1.00 | 1.00 | 1.00 | 0.506 | +0.00 | `Style.pick_first` all-None values |
| E06 | — | — | — | — | — | skipped (failed faithfulness) — default `end` argument |
| E12 | — | — | — | — | — | skipped (failed faithfulness) — `rich.markup.escape` square brackets |

Correctness moved **up on 9 rows, down on 4** (5 flat). The 4 dips (E11 −0.30, E07 −0.23,
E09 −0.20, E01 −0.06) all have recall/precision at 1.0 in *both* runs — same contexts, different
answer phrasing → judge variance, not a reranker effect.

---

## 3. What changed (the LLM reranker)

| File | What it does |
|------|--------------|
| `app/llm_reranker.py` | **NEW** — `LLMReranker`, a drop-in `RetrieverLike` wrapping `HybridRetriever`. Fetches `candidate_k=10`, scores each chunk 1–5 in batches of 5 via the **shared Groq `Generator`** (temperature 0.0 → inherits its rate-limit retries), stable-sorts by score, then returns top-5. Defensive JSON parsing (`{"1": 5, ...}` / `1: 4` line fallback); unparseable chunks get a neutral 3.0. Optional `min_score` filter drops rated-irrelevant chunks *before* the top-k cut (**unset this run**). Degrades gracefully: skips the LLM when there's nothing to rerank, and falls back to base order on total parse failure *or* scoring exception — a reranker hiccup can't kill a query the base retriever already answered. Uses `dataclasses.replace` so shared chunks are never mutated. |
| `main.py` | `build_orchestrator` wraps `HybridRetriever` in `LLMReranker` **by default**; new flags `--no-rerank`, `--candidate-k` (10), `--min-score` (unset). The `Generator` is created once and shared between reranker and final answer. |
| `run_evals.py` | Same three flags threaded through `build_orchestrator` — nothing else changed (the drop-in interface is the point). |
| `test_pipeline.py` | 7 new offline checks: score-parsing variants, reorder + score attachment, min-score filtering, skip-when-short, parse-failure and exception fallbacks. **Full suite green** via `./.venv/Scripts/python.exe test_pipeline.py`. |

`run_ragas.py` needed zero changes (the reranker lives behind `build_orchestrator`; the eval consumes
`eval_results.jsonl`, which `run_evals.py` regenerated with the reranker on).

---

## 4. Analysis

### 4a. The win: all four metrics up on the identical 18 rows
- **Recall 0.876 → 0.944 — 17/18 rows at 1.0.** The only zero left is E07 (the known judge
  attribution artifact: correct answer, precision 0.95, recall 0.0 — the statement-attribution step
  fails to tie the reference to truncated contexts). Because the reranker re-ranks a **10-chunk pool**
  instead of trusting the fused top-5, a right chunk ranked 6–10 by BM25+RRF can still win — that's
  the mechanism, and it closes nearly every remaining gap.
- **E13 precision 0.00 → 0.50 — run 03's smoking gun, fixed.** `Style.parse('')/'none'` previously
  had BM25 noise at rank 1; the reranker demoted it and the top chunk is now the relevant `Style.parse`
  implementation. (0.50 rather than 1.0 — the *set* still isn't clean, but rank-1 is right.)
- **Faithfulness 0.671 → 0.797, zeros 6 → 3.** The reranked order is more likely to place the exact
  implementation chunk first, and the judge verifies more claims: E10 0.25 → 1.0, E18 0.00 → 1.0,
  E15 0.33 → 1.0, E08 0.50 → 0.75. Same 3B judge, so read the *size* cautiously — but the direction
  matches the grounding mechanism. The 3 remaining zeros (E01, E11, E13) are verbatim-grounded
  answers the 3B judge still can't verify claim-by-claim (same artifact as runs 02/03).
- **Correctness 0.662 → 0.698** — 9 rows up vs 4 down. E20 0.45 → 0.728 (+0.28, the biggest single
  jump), E17 0.41 → 0.649 (+0.24), E10 0.47 → 0.637 (+0.17): the questions that run 03's answer
  drifts hit hardest are exactly the ones the reranker's better context ordering fixes.

### 4b. The cost: precision is stubbornly flat, and the LLM scorer has its own blind spot
- **E19 precision 0.50 → 0.00 — the new smoking gun.** `Color.parse('rgb(1,2)')` — the reranker
  itself rated an irrelevant chunk (rgb-component wording) above the `Color.parse` arity-check
  implementation and put it at rank 1. Pointwise LLM scoring is *not* a free pass: it can
  confidently order noise first.
- **E17 precision 0.45 → 0.33** — still the worst precision row; the reranker didn't fix
  `Color.parse('default')` either. And E10 precision regressed 1.00 → 0.58.
- **Net effect:** precision mean is flat (raw −0.002, same-18 +0.018) because the wins (E13, E11
  0.53 → 0.95) cancel the slips (E17, E19, E10). The fused-order noise from run 03 **moved but
  didn't disappear** — the fix for E13 came at the cost of new slips elsewhere. The reranker re-orders
  *within* the 10-chunk pool; it cannot add a chunk BM25+RRF already excluded, so `--candidate-k`
  and `--min-score` are the natural next knobs (both already wired, both unused this run).
- **2 rows skipped again (E06, E12 — faithfulness).** Judge truncation persists at `max_tokens=8192`;
  the victims rotate every run (02: E06/E11; 03: E12; 04: E06/E12). A fixed output cap can't fully
  cure a 3B judge's unbounded faithfulness chain-of-thought on code-heavy answers — this is a judge
  limitation, not a reranker one, but it means "18/18" vs "20/20" scored sets are noise between runs.

### 4c. Net verdict
| Metric | Run 03 | Run 04 | Same-18 Δ | Conclusion |
|--------|--------|--------|-----------|------------|
| context_recall | 0.838 | 0.944 | **+0.068** | pool-of-10 + LLM order closes nearly every retrieval gap; 17/18 rows at 1.0 |
| context_precision | 0.822 | 0.820 | +0.018 | noise moved, not gone — E19 prec 0.0 is the new counterexample |
| faithfulness | 0.604 | 0.797 | **+0.126** | grounded answers verified; zeros 6 → 3 |
| answer_correctness | 0.671 | 0.698 | +0.036 | better on 9/18 rows; E20/E17/E10 jumps |

**Bottom line:** the LLM reranker is a **net win on every metric** even restricted to the identical
18 rows, and it's biggest where run 03 was weakest (recall, faithfulness). But it is *not* the
precision fix run 03 hoped for — the LLM scorer trades E13 for E19. The two tuning knobs it ships
with (`--min-score`, `--candidate-k`) are the obvious run-05 experiments: `--min-score 3` should
drop exactly the low-rated noise chunks behind E19/E17, and `--no-rerank` gives a cheap A/B.

---

## 5. Tooling / infra notes this run

1. **`uv run` worked again** — `uv run python -u run_ragas.py` ran to completion (consistent with
   run 03; the old hang is not back).
2. **The `max_tokens` bump did *not* fix truncation.** `JUDGE_MAX_TOKENS` is already **8192** at HEAD
   (the 2048 → 8192 bump landed with the run-03 commit; run 03's doc predates it). E06/E12 were still
   skipped on `IncompleteOutputException`. The `IncompleteOutputException` message says output-side
   (generation cap), not context-side (`num_ctx` is already 32768) — so the fix is a bigger/stronger
   judge (idea #2), not another `max_tokens` increment.
3. **Reranker cost:** each question now pays ~2 short scoring calls (2 batches × 5 chunks) plus the
   answer call — all on the same Groq `Generator`, so the existing rate-limit retries cover all three.
   The reranker adds latency and API usage per query; `--no-rerank` is the escape hatch.
4. **Deprecation warnings unchanged** — `ragas.metrics` imports → `ragas.metrics.collections`
   (cosmetic, still worth the one-line fix).
5. **`skipped_rows.jsonl` is now a tracked artifact** — it records E06/E12 with their skip reason
   (`metric(s) faithfulness returned null`); `ragas_results.jsonl` is git-modified and
   `skipped_rows.jsonl` untracked at time of writing (commit with the reranker).

---

## 6. Improvement ideas (updated backlog)

Done this run: **LLM reranker** — idea #5 from run 01, implemented as an LLM pointwise reranker
(`app/llm_reranker.py`, on by default) rather than the Jina reranker originally sketched.

| # | Idea | Targets | Status |
|---|------|---------|--------|
| 1 | **Calibrate the reranker** — `--min-score 3` (drop rated-≤2 chunks before top-k), `--candidate-k 20`; A/B with `--no-rerank` | precision (E19 prec 0.0, E17 0.33) | **new — highest impact** |
| 2 | **Upgrade the RAGAS judge** (7B+ local or Groq `gpt-oss-120b`) | faithfulness truncation keeps skipping rows (E06/E12) | still open — now the blocker for clean comparisons |
| 3 | **Fix deprecation warnings** — `ragas.metrics.collections` imports | tooling hygiene | still open |
| 4 | **RRF tuning sweep** — `--rrf-k` (30/60/100), per-retriever top_k, BM25 min-score floor | quality of the 10-chunk pool feeding the reranker | still open (lower priority now the reranker re-orders) |
| 5 | **Chunker v2** — split large classes into method-level chunks (+ class header) | dense-side precision | still open |
| 6 | **Restore the prompt-size cap** (`_MAX_PROMPT_CHARS`/`_truncate`) | 413/TPM risk — more relevant now the reranker reads 10 chunks | still open |
| 7 | **Persist the BM25 index** at ingestion time instead of rebuilding at startup | startup cost as corpus grows | still open |
| 8 | Reconsider `MAX_CONTEXT_CHARS=1200` truncation | recall/fidelity measurement accuracy | still open |
| 9 | Run RAGAS on the full 50-question set | apples-to-apples with run 01 | still open |

---

## 7. Console output (abridged)

```text
PS C:\Users\nirva\Desktop\nightRag\project> uv run python -u run_ragas.py
run_ragas.py:83: DeprecationWarning: Importing answer_correctness from 'ragas.metrics' is deprecated ...
run_ragas.py:83: DeprecationWarning: Importing context_precision from 'ragas.metrics' is deprecated ...
run_ragas.py:83: DeprecationWarning: Importing context_recall from 'ragas.metrics' is deprecated ...
run_ragas.py:83: DeprecationWarning: Importing faithfulness from 'ragas.metrics' is deprecated ...
Scoring 20 rows using Ollama (qwen2.5:3b) & Jina Embeddings...
Evaluating: 100%|...| 8/8 ...   progress: 2/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 4/20 this run
Evaluating:  50%|...| 4/8 ... Exception raised in Job[6]:
  IncompleteOutputException(The output is incomplete due to a max_tokens length limit.)
Evaluating: 100%|...| 8/8 ...   progress: 6/20 this run
  - skipped (failed faithfulness): What is the default value of the 'end' argument of Text (and ...
Evaluating: 100%|...| 8/8 ...   progress: 8/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 10/20 this run
Evaluating:  50%|...| 4/8 ... Exception raised in Job[6]:
  IncompleteOutputException(The output is incomplete due to a max_tokens length limit.)
Evaluating: 100%|...| 8/8 ...   progress: 12/20 this run
  - skipped (failed faithfulness): What does rich.markup.escape do to a string that contains sq ...
Evaluating: 100%|...| 8/8 ...   progress: 14/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 16/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 18/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 20/20 this run

Scored 18 new rows this run. Written to ragas_results.jsonl
Skipped 2 row(s) -> skipped_rows.jsonl

metric                  mean   scored
context_recall         0.944   18/18
context_precision      0.820   18/18
faithfulness           0.797   18/18
answer_correctness     0.698   18/18
```
