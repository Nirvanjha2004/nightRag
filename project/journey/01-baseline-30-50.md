# Run 01 — Baseline (30/50)

**Date:** 2026-08-04
**Command:** `uv run python -u run_evals.py` (equivalent: `./.venv/Scripts/python.exe run_evals.py`)
**Score:** **30/50 passed (60%)**
**Result rows:** `eval_results.jsonl` (one row per question: `{user_input, response, retrieved_contexts, reference}`)

This is the official baseline. Nothing was changed for this run — it captures the state of the
pipeline as it stands after the retry + hyphen-normalization work (see pre-tracking history).

---

## 1. What we're building

**NightRag** — a RAG app that answers questions about the Python `rich` codebase. Given a question
like *"What error does `Color.parse` raise for `color(300)`?"*, it must retrieve the right code
chunks and answer from them, citing `file_path:start_line-end_line` for every claim.

The benchmark is 50 hand-written questions mined from the `rich` test suite. Each question carries
the expected answer plus **keywords**; a question **PASSes iff every keyword appears in the answer**
(case-insensitive, with hyphen variants folded to spaces).

---

## 2. System snapshot (the "current approach")

### Architecture

```
benchmarks/evals.jsonl (50 Q&A pairs)
        │
        ▼
┌────────────────────────────── run_evals.py ──────────────────────────────┐
│  for each question:                                                        │
│    RagOrchestrator.ask(q)                                                  │
│      ├─ Retriever.retrieve(q, top_k=5)                                     │
│      │    ├─ Embedder.embed_query(q)   → Jina API                          │
│      │    └─ VectorDB.query            → Qdrant (local embedded)           │
│      ├─ build_prompt(q, chunks)        → system instructions + chunk blocks│
│      └─ Generator.generate(prompt)     → Groq LLM                          │
│    keyword_score(answer, keywords) → PASS/FAIL                             │
│    row → eval_results.jsonl                                                │
└────────────────────────────────────────────────────────────────────────────┘
```

### Component-by-component

| Stage | File | Implementation |
|-------|------|----------------|
| **Chunking** | `app/chunking.py` | tree-sitter (Python only). V1: chunks **top-level** `function_definition` and `class_definition` only. No nested functions, no imports/docstrings, no size cap. Whole classes stay one chunk (e.g. `Text` ≈ 1,200 lines, `Console` ≈ 2,000 lines). |
| **Embedding** | `app/embedder.py` | Jina AI, model **`jina-embeddings-v5-text-small`**, **1024-dim**, `normalized=True`. Separate `retrieval.passage` / `retrieval.query` tasks. Session-level retries: 3 attempts, backoff 2s→4s→8s, retries 429/503. |
| **Vector DB** | `app/vector_db.py` | **Qdrant, local embedded** (`qdrant_data/`), cosine distance. Collection `code_chunks` = **932 points**. Batch upsert, count sanity check. |
| **Retrieval** | `app/retriever.py` | Pure composition: embed query → `query_points(top_k)` → `RetrievedChunk` (text, file, node type, name, lines, score). No reranking, no hybrid. |
| **Prompt** | `app/prompt_builder.py` | 4 rules: (1) answer only from context, (2) say so explicitly if context is insufficient, (3) cite `file:start-end` for every claim, (4) concise + technical. Chunks rendered as `[Chunk i] file:lines (type: name)` + fenced code. ⚠️ **No size cap currently** (see §6). |
| **Generation** | `app/generator.py` | Groq, model **`openai/gpt-oss-120b`**, `temperature=0.1`, `max_tokens=1024`. Retries **5×** on 429 and 413 `rate_limit_exceeded` with backoff (honors `Retry-After`); genuine 4xx propagate. |
| **Orchestration** | `app/rag_pipeline.py` | `RagOrchestrator.ask(q)`: retrieve → build prompt → generate. Returns answer + chunks + prompt (for tracing). |
| **Eval** | `run_evals.py` | Loads `benchmarks/evals.jsonl`, runs each question, stores `{user_input, response, retrieved_contexts, reference}`, prints live PASS/FAIL + final SCORE. |
| **Offline test** | `test_pipeline.py` | 6 checks: chunk→embed→store→retrieve roundtrip, keyword hyphen normalization, generator retries, embedder retries, prompt cap, eval-row schema. ⚠️ Currently **red** — see §6. |

### Key parameters (as of baseline)

| Parameter | Value |
|-----------|-------|
| Generation model | `openai/gpt-oss-120b` (Groq, free tier) |
| TPM limit | **8,000 tokens/min** (this is what caused the old 413 errors) |
| temperature / max_tokens | 0.1 / 1024 |
| Generator retries | 5 (429, 413 w/ `rate_limit_exceeded`), exponential + Retry-After |
| Embedding model | `jina-embeddings-v5-text-small`, 1024-dim |
| Embedder retries | 3 (429, 503), backoff 2s/4s/8s |
| Vector DB | Qdrant local embedded, cosine, collection `code_chunks`, **932 chunks** |
| Chunker | tree-sitter, top-level defs/classes only, no cap |
| top_k | **5** |
| Eval set | 50 questions, keyword PASS/FAIL |

---

## 3. Score

```
SCORE: 30/50 passed
```

- **PASS (30):** E01, E02, E06, E08, E10, E11, E12, E15, E17, E19, E24, E25, E26, E30, E31, E32,
  E33, E34, E35, E36, E37, E38, E39, E40, E41, E42, E43, E46, E47, E50
- **FAIL (20):** E03, E04, E05, E07, E09, E13, E14, E16, E18, E20, E21, E22, E23, E27, E28, E29,
  E44, E45, E48, E49
- **Errors (0):** none this run — the retries did their job (previous runs lost 5–10 questions to
  413/429/SSL/connection errors).

Full console output for this run is preserved in the user's terminal transcript (also reproducible:
`python run_evals.py`).

---

## 4. Failure analysis (the important part)

All 20 failures fall into three buckets:

### Bucket A — Retrieval gaps: the right chunk never made it into the prompt (9)
The model answered "the implementation isn't in the provided context" — a **retrieval miss**, not a
reasoning failure.

| Id | Question | Missing chunk / reason |
|----|----------|------------------------|
| E04 | `Text.truncate` + ellipsis | Only tests were retrieved, not `Text.truncate` impl → keyword `set_cell_size` missed |
| E05 | `Text.expand_tabs` default tab size | Impl not retrieved → `8` missed |
| E13 | `Style.parse` of `'none'` | `Style.null`/`NULL_STYLE` not in retrieved chunks |
| E16 | `Style.normalize` parse failure | `fallback`/`StyleSyntaxError` not retrieved |
| E20 | `rgb(256,0,0)` → error | **Wrong chunk retrieved** (model answered about `ColorTriplet`, not `Color.parse`) |
| E22 | `Console.render` with `max_width < 1` | Impl not retrieved → `no output` missed |
| E27 | `export_text` without `record=True` | `AssertionError` not retrieved |
| E48 | `Table.add_row` more cells than columns | Impl not retrieved → `extra cells` missed |
| E49 | `Progress.open` bad mode | `ValueError` not retrieved |

**Root causes (hypothesis):**
- Chunks are huge (whole classes), so a class-level chunk is semantically *about* many methods at
  once — the embedding centroid is diluted, and the specific method the question targets isn't
  distinctive enough to win.
- Symbol-name questions (e.g. `Table.add_row`) don't get a lexical boost; pure cosine similarity
  can rank tests above the implementation.

### Bucket B — Keyword mismatches: answer is substantively right, scoring missed it (10)
The model answered correctly but never used the exact keyword phrasing.

| Id | Answer got right | Missing keyword(s) |
|----|------------------|--------------------|
| E03 | raises `TypeError` for `text[::2]` | `__getitem__`, `slice` |
| E07 | returns width 0 for control chars | `cell_len` |
| E09 | splits double-width char into spaces | `cells` (module qualifier, i.e. `cells.split_text`) |
| E14 | `StyleSyntaxError` for `Style.parse('on')` | `background` |
| E18 | `ColorParseError` for `color(300)` | `255` (the literal limit) |
| E21 | prints only the newline | `empty print` |
| E23 | `is_renderable` returns False | `Console.render` |
| E28 | `quiet=True` suppresses all output | `suppress output` |
| E44 | `KeyError` for unknown spinner | `spinner name` |
| E45 | `NoEmoji` for unknown emoji | `emoji name` |

**Root causes (hypothesis):**
- Keyword list is strict (exact substring) and unforgiving of synonyms, plurals, and module
  qualifiers.
- Some keywords test *phrasing* more than *understanding* (`empty print`, `suppress output`,
  `spinner name`).

### Bucket C — Hallucination / wrong answer (1)
| Id | Question | What went wrong |
|----|----------|-----------------|
| E29 | `console.line(-1)` | Model reasoned `"\n" * -1` → empty string → "no exception". The real code **asserts** `count >= 0` → `AssertionError`. It had the right source (`NewLine`) but didn't check the guard. |

### ⚠️ Scoring blind spots (also part of the story)
- **Non-answers can PASS.** E15 and E40 "passed" even though the model literally said *"I'm sorry,
  the provided code context does not include..."* — the keywords happened to be mentioned in the
  apology. The keyword check can't tell a real answer from a graceful "I don't know".
- This means the true ceiling of this eval as a *quality* metric is fuzzy; it's a good
  **regression** metric, not a perfect quality judge.

---

## 5. What already works (credits for the current score)

- **Generator retries** (429/413 with backoff + `Retry-After`): zero error-lost questions this run
  (was ~10 at 24/50).
- **Embedder retries** (429/503, 2s→4s→8s): killed the SSL/connection aborts from run #2.
- **Hyphen normalization** in `keyword_score` (fold U+2011 & friends to spaces on both sides):
  E09/E12-class false FAILs fixed.
- **Dataset-style output** (`{user_input, response, retrieved_contexts, reference}`) — ready for
  downstream RAG evaluation tooling.

---

## 6. Known issues carried into the journey

1. **`test_pipeline.py` is currently red.** `_check_prompt_cap` imports `_MAX_PROMPT_CHARS` and
   `_truncate` from `app.prompt_builder.py`, but those were lost from the source (only a stale
   `.pyc` still has them). The offline suite fails at that check with `ImportError`.
   → Restoration is improvement-idea #3.
2. **No prompt-size cap** in `build_prompt`. The 8k TPM limit is why large-class retrievals produced
   413 errors in earlier runs. This run got lucky (no oversized retrievals), but it's a landmine.
3. **`uv run` hangs** on this machine (even `print('hi')` stalls — likely a uv sync/network issue).
   Workaround: `./.venv/Scripts/python.exe ...`.
4. **Debug noise** (`debug2 debug3 debug4 debug5 debug1`) printed before every answer in this run's
   output. Not present in the current source (removed since the run) — ignored per instruction, but
   worth keeping out of future commits.
5. **932 chunks / whole-class chunking** means some chunks are enormous (multi-thousand-line
   classes) — embedding quality and prompt cost both suffer.

---

## 7. Improvement hypotheses to test next (ordered)

1. **Chunker v2 — split large classes into method chunks** (+ prepend the class header as context).
   Directly attacks the 9 retrieval-gap failures and reduces prompt bloat. Highest expected gain.
2. **Make the eval honest**: relax keyword matching (word-boundary, plural/verb forms, module
   qualifiers) and/or require the answer to contain a non-trivial claim. Fixes the 10
   keyword-mismatch failures and the false-PASS blind spot — gives us a trustworthy score to
   optimize against.
3. **Restore the prompt-size cap** (also repairs `test_pipeline.py`).
4. **Hybrid retrieval** (BM25 + dense, RRF merge) to help symbol-name questions like E48/E49.
5. **Reranker** on top-20 → top-5.
6. **top_k sweep** (3/5/8) + min-score threshold.
7. **Module-level context chunks** (file docstrings/imports) as an extra retrieval source.
8. **Query rewriting** for symbol questions (append `function_definition`/`class_definition`).
9. **Generation tuning**: `max_tokens` headroom, alternate models.

Each of these gets its own journal entry (`NN-title-score.md`) so the journey is auditable.
