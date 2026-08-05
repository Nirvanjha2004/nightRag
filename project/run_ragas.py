"""
run_ragas.py — score eval_results.jsonl (from run_evals.py) with RAGAS using Ollama (Qwen3 8B).

Usage:
    python run_ragas.py            # score everything
    python run_ragas.py 5          # smoke test: only score first 5 rows
"""

import json
import math
import os
import sys
import types

RESULTS_FILE = "eval_results.jsonl"
OUTPUT_FILE = "ragas_results.jsonl"

OLLAMA_BASE_URL = "http://localhost:11434/v1"
JUDGE_MODEL = "qwen3:8b"
EMBED_MODEL = "jina-embeddings-v5-text-small"

# Clip each context so judge prompts stay comfortably inside budget.
MAX_CONTEXT_CHARS = 1200


# ragas unconditionally tries to import VertexAI from langchain_community,
# which no longer ships those modules. Stub it out so the import doesn't crash.
def _stub_vertexai():
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
from ragas.metrics import (
    answer_correctness,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig

from app.config import load_env

METRICS = [context_recall, context_precision, faithfulness, answer_correctness]


def load_rows(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in open(RESULTS_FILE, encoding="utf-8") if line.strip()]
    rows = [r for r in rows if r.get("response")]  # skip empty answers, RAGAS can't score those
    for r in rows:
        r["retrieved_contexts"] = [
            c if len(c) <= MAX_CONTEXT_CHARS else c[:MAX_CONTEXT_CHARS] + "...(truncated)"
            for c in r.get("retrieved_contexts", [])
        ]
    return rows[:limit] if limit else rows


def clean(value):
    """NaN/Inf -> None so json.dump doesn't choke."""
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    load_env()
    if not os.environ.get("jina_api_key"):
        print("Missing jina_api_key in .env (required for Jina embeddings)")
        return 1

    rows = load_rows(limit)
    if not rows:
        print(f"No scorable rows in {RESULTS_FILE}")
        return 1
    print(f"Scoring {len(rows)} rows using local Ollama ({JUDGE_MODEL})...")

    # Point OpenAI client to Ollama's local endpoint
    llm = llm_factory(
        JUDGE_MODEL,
        client=OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL),
        max_tokens=4096,
    )

    embeddings = OpenAIEmbeddings(
        client=AsyncOpenAI(api_key=os.environ["jina_api_key"], base_url="https://api.jina.ai/v1"),
        model=EMBED_MODEL,
    )

    # evaluate() automatically binds llm and embeddings to the metrics
    result = evaluate(
        EvaluationDataset.from_list(rows),
        metrics=METRICS,
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=120, max_retries=2, max_wait=15, max_workers=1),
    )

    out_rows = [
        {**row, **{m.name: clean(scores.get(m.name)) for m in METRICS}}
        for row, scores in zip(rows, result.scores)
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'metric':<20}{'mean':>8}   scored")
    for m in METRICS:
        vals = [r[m.name] for r in out_rows if r[m.name] is not None]
        mean = sum(vals) / len(vals) if vals else float("nan")
        print(f"{m.name:<20}{mean:>8.3f}   {len(vals)}/{len(out_rows)}")

    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    sys.exit(main())