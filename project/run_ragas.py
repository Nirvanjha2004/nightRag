"""
run_ragas.py — score eval_results.jsonl (from run_evals.py) with RAGAS using Ollama.

Checkpointed:
- Uses local Ollama for the LLM judge (Qwen 2.5 3B).
- Uses Jina AI API for embeddings (kept as requested).
- Writes each batch to OUTPUT_FILE immediately and skips already-scored rows
  on the next run, so a crash never loses prior progress.

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

# --- LOCAL OLLAMA & REMOTE JINA CONFIG ---
OLLAMA_BASE_URL = "http://localhost:11434/v1"
JINA_BASE_URL = "https://api.jina.ai/v1"

# Fast, lightweight model fitting easily inside 4GB VRAM
JUDGE_MODEL = "qwen2.5:3b"  # Alternative: "llama3.2:3b"
EMBED_MODEL = "jina-embeddings-v5-text-small"

# Clip context lengths to keep inference speed high on local GPU
# MAX_CONTEXT_CHARS = 1200

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
    """Questions already present in OUTPUT_FILE — skip these on resume."""
    if not os.path.exists(OUTPUT_FILE):
        return set()
    scored = set()
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    scored.add(json.loads(line)["user_input"])
                except (json.JSONDecodeError, KeyError):
                    continue  # ignore a corrupt trailing line
    return scored


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


def print_summary():
    """Read OUTPUT_FILE fresh and print current means."""
    if not os.path.exists(OUTPUT_FILE):
        return
    rows = [json.loads(line) for line in open(OUTPUT_FILE, encoding="utf-8") if line.strip()]
    print(f"\n{'metric':<20}{'mean':>8}   scored")
    for m in METRICS:
        vals = [r[m.name] for r in rows if r.get(m.name) is not None]
        mean = sum(vals) / len(vals) if vals else float("nan")
        print(f"{m.name:<20}{mean:>8.3f}   {len(vals)}/{len(rows)}")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    load_env()
    # Only Jina API key is required now (Ollama runs locally)
    if not os.environ.get("jina_api_key"):
        print("Missing jina_api_key in .env")
        return 1

    rows = load_rows(limit)
    already_scored = load_scored_questions()
    rows = [r for r in rows if r["user_input"] not in already_scored]

    if not rows:
        print(f"Nothing left to score ({len(already_scored)} rows already in {OUTPUT_FILE}).")
        print_summary()
        return 0

    print(f"Scoring {len(rows)} rows using Ollama ({JUDGE_MODEL}) & Jina Embeddings...")

    # Configure LLM to point to local Ollama server via OpenAI client wrapper
    llm = llm_factory(
        JUDGE_MODEL,
        client=OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL),
        max_tokens=2048,
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
                out = {**row, **{m.name: clean(scores.get(m.name)) for m in METRICS}}
                f_out.write(json.dumps(out, ensure_ascii=False) + "\n")
                f_out.flush()
                scored_this_run += 1

            print(f"  progress: {min(i + BATCH_SIZE, len(rows))}/{len(rows)} this run")

            if i + BATCH_SIZE < len(rows):
                time.sleep(BATCH_COOLDOWN_SECONDS)

    print(f"\nScored {scored_this_run} new rows this run. Written to {OUTPUT_FILE}")
    print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())