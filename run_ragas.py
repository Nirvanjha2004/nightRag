"""
run_ragas.py — score eval_results.jsonl (from run_evals.py) with RAGAS using Ollama.

Checkpointed:
- Uses local Ollama for the LLM judge (Qwen 2.5 3B).
- Uses Jina AI API for embeddings (kept as requested).
- Writes each batch to OUTPUT_FILE immediately and skips already-scored rows
  on the next run, so a crash never loses prior progress.

Skip instead of scoring garbage:
- Rows whose total prompt (question + answer + contexts) would exceed the
  judge model's context window are skipped UP FRONT, before any LLM call.
- Rows where a metric still fails mid-run (judge output truncated ->
  IncompleteOutputException) are skipped per-row and recorded in
  SKIPPED_FILE with a reason, instead of writing a broken `null` score.
- Skipped rows are tracked, so a re-run does not retry them. Rows that were
  written earlier with a `null` metric are treated as *not* scored and get
  retried. A retried row that succeeds appends a fresh line; the summary
  keeps the latest version of each question.

Usage:
    python run_ragas.py            # score everything not yet scored
    python run_ragas.py 20         # only consider first 20 rows from eval_results.jsonl
"""

import json
import math
import os
import sys
import time
import types

RESULTS_FILE = "eval_results.jsonl"
OUTPUT_FILE = "ragas_results.jsonl"
SKIPPED_FILE = "skipped_rows.jsonl"

# --- LOCAL OLLAMA & REMOTE JINA CONFIG ---
OLLAMA_BASE_URL = "http://localhost:11434/v1"
JINA_BASE_URL = "https://api.jina.ai/v1"

# Fast, lightweight model fitting easily inside 4GB VRAM
JUDGE_MODEL = "qwen2.5:3b"  # Alternative: "llama3.2:3b"
EMBED_MODEL = "jina-embeddings-v5-text-small"

# --- Judge LLM limits ---
# qwen2.5:3b ships with a 32k-token window; Ollama's default num_ctx is much
# smaller, so bump it explicitly or long prompts get silently truncated.
NUM_CTX = 32768
# "IncompleteOutputException: ... max_tokens length limit" means the model hit
# the generation cap mid-thought (faithfulness uses long chain-of-thought).
# 4096 was too tight -> 8192 gives it room to finish.
JUDGE_MAX_TOKENS = 8192
# Rough chars-per-token estimate used by the pre-filter budget check.
CHARS_PER_TOKEN = 4
# Rows whose estimated prompt exceeds this budget are skipped up front
# (context window minus output budget, minus a safety margin).
PROMPT_BUDGET_TOKENS = NUM_CTX - JUDGE_MAX_TOKENS - 2048

# Local execution batch configuration
BATCH_SIZE = 2
BATCH_COOLDOWN_SECONDS = 1    # Minimal delay needed since local Ollama has no rate limit
MAX_BATCH_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 5


def _stub_vertexai():
    # ragas unconditionally tries to import VertexAI from langchain_community
    for fullname, attr in [
        ("langchain_community.chat_models.vertexai", "ChatVertexAI"),
        ("langchain_community.llms.vertexai", "VertexAI"),
    ]:
        module = types.ModuleType(fullname)
        setattr(module, attr, type(attr, (), {}))
        sys.modules[fullname] = module


_stub_vertexai()

from openai import AsyncOpenAI, OpenAI
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics import answer_correctness, context_precision, context_recall, faithfulness
from ragas.run_config import RunConfig

from app.config import load_env

METRICS = [context_recall, context_precision, faithfulness, answer_correctness]


def load_rows(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in open(RESULTS_FILE, encoding="utf-8") if line.strip()]
    rows = [r for r in rows if r.get("response")]  # skip empty answers, RAGAS can't score those
    # for r in rows:
    #     r["retrieved_contexts"] = [
    #         c if len(c) <= MAX_CONTEXT_CHARS else c[:MAX_CONTEXT_CHARS] + "...(truncated)"
    #         for c in r.get("retrieved_contexts", [])
    #     ]
    return rows[:limit] if limit else rows


def load_scored_questions() -> set[str]:
    """Questions in OUTPUT_FILE that have EVERY metric scored (non-null).

    Rows carrying a `null` metric (a metric that failed to score) are treated
    as *not* scored, so they get re-tried on the next run instead of silently
    polluting the summary with a partial/broken score.
    """
    if not os.path.exists(OUTPUT_FILE):
        return set()
    scored = set()
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # ignore a corrupt trailing line
            if all(row.get(m.name) is not None for m in METRICS):
                scored.add(row["user_input"])
    return scored


def load_skipped_questions() -> set[str]:
    """Questions already recorded in SKIPPED_FILE — do not retry these."""
    if not os.path.exists(SKIPPED_FILE):
        return set()
    skipped = set()
    with open(SKIPPED_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                skipped.add(json.loads(line)["user_input"])
            except (json.JSONDecodeError, KeyError):
                continue
    return skipped


def estimated_tokens(row: dict) -> int:
    """Rough token estimate for the full prompt a row will produce."""
    text = row.get("user_input", "") + "\n" + row.get("response", "")
    for ctx in row.get("retrieved_contexts", []):
        text += "\n" + ctx
    return len(text) // CHARS_PER_TOKEN


def clean(value):
    """NaN/Inf -> None so json.dump doesn't choke."""
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value


def run_batch_with_backoff(batch, llm, embeddings, run_config):
    """Run one batch with retry logic."""
    for attempt in range(1, MAX_BATCH_RETRIES + 1):
        try:
            return evaluate(
                EvaluationDataset.from_list(batch),
                metrics=METRICS,
                llm=llm,
                embeddings=embeddings,
                run_config=run_config,
            )
        except Exception as e:
            if attempt < MAX_BATCH_RETRIES:
                print(f"  batch error (attempt {attempt}/{MAX_BATCH_RETRIES}): {e}, retrying in {RATE_LIMIT_WAIT_SECONDS}s...")
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            raise


def _last_scored_rows() -> list[dict]:
    """Valid rows from OUTPUT_FILE, deduped by question (latest line wins)."""
    by_q: dict[str, dict] = {}
    if not os.path.exists(OUTPUT_FILE):
        return []
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "user_input" not in row:
                continue
            if all(row.get(m.name) is not None for m in METRICS):
                by_q[row["user_input"]] = row  # later line overwrites earlier one
    return list(by_q.values())


def print_summary():
    """Read OUTPUT_FILE / SKIPPED_FILE fresh and print current means."""
    rows = _last_scored_rows()

    # Count distinct skipped questions: a row is appended to SKIPPED_FILE once
    # per run it fails, so dedupe or the reported number drifts upward.
    skipped = set()
    if os.path.exists(SKIPPED_FILE):
        with open(SKIPPED_FILE, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    skipped.add(json.loads(line)["user_input"])
                except (json.JSONDecodeError, KeyError):
                    continue

    print(f"\n{'metric':<20}{'mean':>8}   scored")
    for m in METRICS:
        vals = [r[m.name] for r in rows if r.get(m.name) is not None]
        mean = sum(vals) / len(vals) if vals else float("nan")
        print(f"{m.name:<20}{mean:>8.3f}   {len(vals)}/{len(rows)}")
    if skipped:
        print(f"\n{len(skipped)} row(s) skipped (context too long or metric failure) -> {SKIPPED_FILE}")


def main():
    # Same Windows-console guard as run_evals.py — replace exotic chars instead
    # of crashing on cp1252 (question snippets are printed during scoring).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    load_env()
    # Only Jina API key is required now (Ollama runs locally)
    if not os.environ.get("jina_api_key"):
        print("Missing jina_api_key in .env")
        return 1

    rows = load_rows(limit)
    already_scored = load_scored_questions()
    already_skipped = load_skipped_questions()
    rows = [r for r in rows if r["user_input"] not in already_scored | already_skipped]

    # --- Pre-filter: skip rows whose prompt would overflow the context window ---
    candidates = rows
    too_long, rows = [], []
    for r in candidates:
        tok = estimated_tokens(r)
        if tok > PROMPT_BUDGET_TOKENS:
            r["skip_reason"] = f"estimated {tok} tokens exceeds budget {PROMPT_BUDGET_TOKENS}"
            too_long.append(r)
        else:
            rows.append(r)

    skipped_this_run = 0
    skipped_rows: list[dict] = []  # rows that failed mid-eval, written to SKIPPED_FILE at the end

    # SKIPPED_FILE is only touched when there is actually something to record.
    if too_long:
        with open(SKIPPED_FILE, "a", encoding="utf-8") as f_skip:
            for r in too_long:
                f_skip.write(json.dumps(r, ensure_ascii=False) + "\n")
        skipped_this_run += len(too_long)
        print(f"Skipped {len(too_long)} rows up front (context too long) -> {SKIPPED_FILE}")
        for r in too_long:
            print(f"  - {r['user_input'][:70]}")

    if not rows:
        print(f"Nothing left to score ({len(already_scored)} rows already in {OUTPUT_FILE}).")
        print_summary()
        return 0

    print(f"Scoring {len(rows)} rows using Ollama ({JUDGE_MODEL}) & Jina Embeddings...")

    # Configure LLM to point to local Ollama server via OpenAI client wrapper.
    # extra_body={"num_ctx": ...} is forwarded verbatim by the OpenAI SDK,
    # so Ollama actually uses the model's full 32k context window.
    llm = llm_factory(
        JUDGE_MODEL,
        client=OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL),
        max_tokens=JUDGE_MAX_TOKENS,
        extra_body={"num_ctx": NUM_CTX},
    )

    # Configure Jina Embeddings as before
    embeddings = OpenAIEmbeddings(
        client=AsyncOpenAI(api_key=os.environ["jina_api_key"], base_url=JINA_BASE_URL),
        model=EMBED_MODEL,
    )
    run_config = RunConfig(timeout=120, max_retries=2, max_wait=15, max_workers=1)

    scored_this_run = 0
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f_out:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            try:
                result = run_batch_with_backoff(batch, llm, embeddings, run_config)
            except Exception as e:
                print(f"\nBatch {i // BATCH_SIZE + 1} failed permanently: {e}")
                print(f"Stopping here — {scored_this_run} rows scored and saved this run.")
                print("Rerun the script to resume from where you left off.")
                break

            for row, scores in zip(batch, result.scores):
                score_map = {m.name: clean(scores.get(m.name)) for m in METRICS}
                missing = [m for m, v in score_map.items() if v is None]
                if missing:
                    # A metric failed for this row (e.g. truncated judge
                    # output). Record it as skipped instead of writing a
                    # broken `null` score into the results file.
                    row["skip_reason"] = "metric(s) " + ", ".join(missing) + " returned null"
                    skipped_rows.append(row)
                    print(f"  - skipped (failed {', '.join(missing)}): {row['user_input'][:60]}...")
                    continue
                f_out.write(json.dumps({**row, **score_map}, ensure_ascii=False) + "\n")
                f_out.flush()
                scored_this_run += 1

            print(f"  progress: {min(i + BATCH_SIZE, len(rows))}/{len(rows)} this run")

            if i + BATCH_SIZE < len(rows):
                time.sleep(BATCH_COOLDOWN_SECONDS)

    # Write post-evaluation skips at the end (a crash mid-batch at worst loses
    # a skip record, which simply gets retried on the next run).
    if skipped_rows:
        with open(SKIPPED_FILE, "a", encoding="utf-8") as f_skip:
            for r in skipped_rows:
                f_skip.write(json.dumps(r, ensure_ascii=False) + "\n")
        skipped_this_run += len(skipped_rows)

    print(f"\nScored {scored_this_run} new rows this run. Written to {OUTPUT_FILE}")
    if skipped_this_run:
        print(f"Skipped {skipped_this_run} row(s) -> {SKIPPED_FILE}")
    print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
