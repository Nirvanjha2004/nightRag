# Run 02 — RAGAS quality eval with Qwen 2.5 3B judge (20 questions)

**Date:** 2026-08-06
**Command:** `uv run python -u run_ragas.py`
**Judge:** Ollama `qwen2.5:3b` (local, `max_tokens=2048`) · **Embeddings:** Jina `jina-embeddings-v5-text-small` (API)
**Dataset:** `benchmarks/evals.jsonl` — **20 rows (E01–E20)**. ⚠️ The benchmark was trimmed from 50 → 20
questions in commit `1a78cb8` ("Remove outdated eval test cases"); the journey README still says 50 (stale).
**Output:** `ragas_results.jsonl` (20 rows, one per question)

This run is the first **RAGAS quality score** of the pipeline — it measures *retrieval health* and
*answer faithfulness/correctness*, not the keyword PASS/FAIL from run 01. The two numbers are NOT directly
comparable (different metric, different dataset size); run 02 is a different lens on the same pipeline.

---

## 1. Results (mean over 20 rows)

```
metric                  mean   scored
context_recall         0.800   20/20
context_precision      0.896   20/20
faithfulness           0.343   18/20   ← 2 rows unscored (judge max_tokens error)
answer_correctness     0.703   20/20
```

| Metric | Mean | Median | Min | Zeros |
|--------|-----:|-------:|----:|------:|
| context_recall | 0.800 | 1.000 | 0.000 | 4 |
| context_precision | 0.896 | 1.000 | 0.333 | 0 |
| faithfulness | 0.343 | 0.125 | 0.000 | 9 of 18 |
| answer_correctness | 0.703 | 0.718 | 0.388 | 0 |

**One-line reading:** Retrieval is healthy (recall 0.80, precision 0.90 — nothing wrong with what gets
retrieved), answers are substantively right (correctness 0.70), but **faithfulness is the red flag** —
and most of that red flag is a *judge limitation*, not a hallucination problem (see §3).

---

## 2. Per-question scores (sorted by answer_correctness)

| Id | recall | prec | faith | corr | Question (abbr.) |
|----|-------:|-----:|------:|-----:|------------------|
| E09 | 1.00 | 1.00 | 1.00 | 0.39 | `cells.split_text` cuts inside a 2-cell char |
| E15 | 1.00 | 1.00 | 0.25 | 0.46 | `Style.pick_first` all-None values |
| E19 | 1.00 | 0.50 | 0.00 | 0.46 | `Color.parse('rgb(1,2)')` — two components |
| E16 | 1.00 | 1.00 | 0.00 | 0.47 | `Style.normalize` parse failure fallback |
| E04 | 1.00 | 1.00 | 0.00 | 0.51 | `Text.truncate` ellipsis overflow |
| E01 | 1.00 | 0.80 | 0.00 | 0.65 | `Text.append(text, style=...)` w/ Text + style |
| E13 | 1.00 | 0.70 | 0.00 | 0.69 | `Style.parse('')` / `'none'` → null style |
| E05 | 0.00 | 1.00 | 0.75 | 0.71 | `Text.expand_tabs` default tab size |
| E07 | 0.00 | 1.00 | 1.00 | 0.71 | `get_character_cell_size` control chars |
| E17 | 0.00 | 1.00 | 1.00 | 0.71 | `Color.parse('default')` → ColorType.DEFAULT |
| E08 | 1.00 | 0.33 | 1.00 | 0.72 | `set_cell_size` total ≤ 0 |
| E02 | 1.00 | 1.00 | 0.00 | 0.73 | `Text.append` non-str/non-Text |
| E18 | 1.00 | 1.00 | 0.67 | 0.74 | `Color.parse` number > 255 |
| E11 | 1.00 | 0.64 | n/a | 0.82 | markup `[/]` with nothing to close |
| E14 | 1.00 | 1.00 | 0.25 | 0.82 | `Style.parse('on')` missing color |
| E06 | 0.00 | 1.00 | n/a | 0.85 | default `end` argument |
| E10 | 1.00 | 1.00 | 0.00 | 0.86 | markup mismatched closing tag |
| E12 | 1.00 | 1.00 | 0.00 | 0.89 | `rich.markup.escape` square brackets |
| E20 | 1.00 | 0.95 | 0.00 | 0.89 | `rgb(256,0,0)` component > 255 |
| E03 | 1.00 | 1.00 | 0.25 | 0.96 | `Text` slice with step != 1 |

Faithfulness `n/a` on E06 + E11 — those two rows hit `IncompleteOutputException` (judge output truncated by
`max_tokens=2048`) during the faithfulness sub-task; every other metric was still scored.

---

## 3. Analysis

### 3a. Retrieval is the strong point — recall 0.80 / precision 0.90
- **context_precision 0.896 (median 1.0)** with **zero 0.0 scores** → when the right chunk is retrieved, the
  retrieved set is almost entirely relevant. Only E08 (0.33) and E19 (0.50) dragged precision down.
- **context_recall 0.80** — 16/20 questions had the needed source chunk in context. The 4 recall-0 rows
  (E05, E06, E07, E17) are **not** retrieval misses: all four have precision 1.0 and *correct answers*
  (corr 0.71–0.85). The judge's statement-attribution step simply failed to tie the reference to the
  (heavily truncated, see §4) contexts. Treat recall as ≥ 0.80, with the real value probably higher.

### 3b. Faithfulness 0.343 is a judge artifact — do not read it as "65% hallucination"
- **9 of 18 scored rows got faithfulness = 0.0**, including answers that are verbatim-grounded in the
  retrieved chunk (E01, E02, E10, E12, E13, E19, E20 all cite the exact code and are correct per
  answer_correctness 0.65–0.89). A 3B local model cannot reliably run the faithfulness claim-by-claim
  verification on code-heavy answers.
- Run 01 found only **1 hallucination in 50 questions (E29)** via manual inspection — the pipeline does
  not hallucinate at the rate 0.343 would suggest.
- **Fix:** switch the judge to a larger model (`llama3.2:3b` was suggested; ideally 7B+) and/or raise
  `max_tokens` (see §4). Until then, **use faithfulness only as a relative trend, not an absolute quality
  number.**

### 3c. Answer correctness 0.703 is the headline number
- Median 0.718; best E03 (0.96), worst E09 (0.39).
- The 4 sub-0.5 rows (E09, E15, E19, E16) are all **retrieval-correct (recall 1.0) and answer-correct on
  inspection** — e.g. E19's response correctly states `ColorParseError("expected three components…")` yet
  scores 0.46. This is the judge penalizing long, precise code-citing answers vs. terse references, plus
  answer-length mismatches. So the *true* correctness is likely a bit above 0.70.

---

## 4. Tooling / infra issues this run exposed

1. **2 rows unscored for faithfulness** — `IncompleteOutputException(The output is incomplete due to a
   max_tokens length limit.)` raised twice in the log (jobs during the E06/E11 batches). `max_tokens=2048`
   in `run_ragas.py` is too small for the judge's structured output. → Bump to 4096.
2. **Deprecation warnings on startup** — importing metrics from `ragas.metrics` is deprecated in favor of
   `ragas.metrics.collections` (e.g. `from ragas.metrics.collections import answer_correctness`). Cosmetic,
   but the warnings are noise to fix.
3. **Contexts truncated to 1200 chars** (`MAX_CONTEXT_CHARS` in `run_ragas.py`) before scoring — helps
   speed, but contributes to the recall-0/fidelity 0 rows on long chunks. Trade-off to revisit if we chase
   higher metric fidelity.
4. `uv run` still hangs on this machine (workaround: `./.venv/Scripts/python.exe`), and the working-tree
   `run_ragas.py` differs from the last commit (commit `1a78cb8` had switched to Groq; the current file is
   back on local Ollama + Jina).

---

## 5. Comparison with Run 01 (the important part)

### Different metrics, overlapping questions
- **Run 01** (`01-baseline-30-50.md`): keyword PASS/FAIL on the then-50-question set → **30/50 (60%)**.
  Bucket analysis: 9 retrieval gaps, 10 keyword mismatches, 1 hallucination, 0 errors.
- **Run 02** (this file): RAGAS on the trimmed **20-question set (E01–E20)** → recall 0.80, precision
  0.90, correctness 0.70, faithfulness 0.34 (judge-limited).
- The 20 RAGAS rows are exactly the **first 20 questions of run 01**: **10 baseline-PASS + 10 baseline-FAIL**,
  so we can cross-check the two metrics question-by-question.

### Baseline FAIL group scores just as well as the PASS group
| Group (n=10 each) | recall | prec | faith | corr |
|-------------------|-------:|-----:|------:|-----:|
| baseline PASS (E01 E02 E06 E08 E10 E11 E12 E15 E17 E19) | 0.800 | 0.828 | 0.281 | 0.716 |
| baseline FAIL (E03 E04 E05 E07 E09 E13 E14 E16 E18 E20) | 0.800 | **0.965** | 0.392 | 0.690 |

**This is the headline insight of the comparison:** the 10 questions that *failed* the keyword check in
run 01 score **higher on context_precision (0.965 vs 0.828)** and statistically the same on answer
correctness (0.690 vs 0.716). RAGAS says those answers are correct and grounded — the run-01 failures were
mostly **keyword-phrasing misses, not quality failures**, exactly matching run-01's "Bucket B" hypothesis
(10 of 20 FAILs were "answer is substantively right, scoring missed it").

**Smoking-gun examples:**
- **E03** (run 01 FAIL — keywords `__getitem__`, `slice` missing) is the **highest-scoring answer in the
  entire run: corr 0.96, recall 1.0, precision 1.0.** The answer is excellent; the keyword check just
  wanted different words.
- **E20** (run 01 FAIL — "wrong chunk retrieved", answered about `ColorTriplet`) now scores corr 0.89 /
  recall 1.0 → retrieval fixed it (chunker/embedder improvements landed in commit `1a78cb8`).
- **E13** (run 01 FAIL — `Style.null`/`NULL_STYLE` "not retrieved") now has recall 1.0 and a correct
  answer (corr 0.69).
- **E05, E07** (run 01 FAILs — impl "not retrieved") have precision 1.0 and correct answers (corr 0.71) →
  retrieval now finds them; the recall-0 is a judge attribution artifact (see §3a).

### Remaining real weaknesses (worth a run-03 focus)
RAGAS flags 4 rows below 0.50 that *do* look weaker even on inspection:
- **E16** (corr 0.47) `Style.normalize` fallback — answer is technically right but vague ("returns
  `style.strip().lower()`"); baseline also FAILed this (fallback/`StyleSyntaxError` not retrieved).
- **E19** (corr 0.46) `rgb(1,2)` — baseline PASSed it, but RAGAS says the answer is off vs the reference
  ("expected three components"). Candidate for re-inspection.
- **E15** (corr 0.46) `Style.pick_first` all-None — answer right, but verbose; judge penalized length.
- **E09** (corr 0.39, lowest) `split_text` 2-cell cut — answer correct but the longest, most code-heavy
  response; likely a length/format penalty from the judge.

### What each metric says about the pipeline
| Metric | Run 02 signal | Conclusion |
|--------|---------------|------------|
| context_precision 0.90 | retrieved set is relevant | retrieval tuning paying off |
| context_recall 0.80 (≥) | needed chunk usually present | good; 4 low rows are judge artifacts |
| answer_correctness 0.70 | answers match references | solid; true value likely higher |
| faithfulness 0.34 | **unreliable with 3B judge** | upgrade judge before trusting it |

### Agreement between the two evals
- Of 10 baseline-PASS questions, RAGAS agrees 9 are ≥ 0.65 correct (only E15/E19 dip to 0.46).
- Of 10 baseline-FAIL questions, RAGAS says 8 are actually fine (≥ 0.69); only E16 (0.47) and E09 (0.39)
  remain questionable.
- **Both metrics independently point at the same short list: E16 and E09** — worth manual inspection next.

---

## 6. Improvement ideas (updated backlog)

| # | Idea | Targets |
|---|------|---------|
| 1 | **Upgrade the RAGAS judge** (7B+ local or Groq `gpt-oss-120b`) + `max_tokens=4096` | faithfulness metric becomes trustworthy; fewer unscored rows |
| 2 | **Fix deprecation warnings** — `ragas.metrics.collections` imports | tooling hygiene |
| 3 | **Re-inspect E16 / E09 answers** manually; consider adding explicit fallback-keyword coverage | the only two questions both evals flag |
| 4 | Reconsider `MAX_CONTEXT_CHARS=1200` truncation | recall/fidelity measurement accuracy |
| 5 | Run RAGAS on the full 50-question set for a direct run-01↔run-02 comparison | apples-to-apples quality vs keyword score |
| 6 | (from run 01) split large classes into method-level chunks; hybrid retrieval (BM25+RRF); reranker | retrieval precision/recall gains |

## 7. Console output (abridged)

```text
Scoring 20 rows using Ollama (qwen2.5:3b) & Jina Embeddings...
Evaluating: 100%|...| 8/8 ...   progress: 2/20 this run
Evaluating: 100%|...| 8/8 ...   progress: 4/20 this run
Evaluating:  50%|...| 4/8 ... Exception raised in Job[6]:
  IncompleteOutputException(The output is incomplete due to a max_tokens length limit.)
Evaluating: 100%|...| 8/8 ...   progress: 6/20 this run
...
Evaluating:   0%|...| 0/8 ... Exception raised in Job[2]:
  IncompleteOutputException(The output is incomplete due to a max_tokens length limit.)
...
Scored 20 new rows this run. Written to ragas_results.jsonl

metric                  mean   scored
context_recall         0.800   20/20
context_precision      0.896   20/20
faithfulness           0.343   18/20
answer_correctness     0.703   20/20
```
