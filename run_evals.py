"""
run_evals.py — run the golden benchmark (benchmarks/evals.jsonl) through the
full RAG pipeline and store one dataset row per question:

    {
        "user_input": question,
        "response": answer,
        "retrieved_contexts": [retrieved chunk texts],
        "reference": expected_answer,
    }

Rows are written to eval_results.jsonl; a keyword-hit PASS/FAIL summary is
printed to the console as a cheap live check. For the authoritative scores,
run run_ragas.py on the generated file (context recall, context precision,
answer correctness, faithfulness).

Usage (ingest first, then):
    python run_evals.py
    python run_ragas.py

The LLM reranker is on by default (see main.build_orchestrator) — pass
--no-rerank to evaluate the raw hybrid retrieval path. Corrective RAG is also
on by default (retrieval evaluator + query rewrite + knowledge refinement) —
pass --no-crag to evaluate plain reranked RAG. Each row records the CRAG
verdict in "crag_verdict" (None when CRAG is off).
"""

import argparse
import json
import sys
from pathlib import Path

from main import build_orchestrator

EVALS_FILE = "benchmarks/evals.jsonl"
RESULTS_FILE = "eval_results.jsonl"


def load_evals(path: str = EVALS_FILE) -> list[dict]:
    evals = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        evals.append(json.loads(line))
    return evals


# Hyphen look-alikes the model occasionally emits instead of a plain hyphen or a
# space (e.g. non-breaking hyphen U+2011 in 'double‐width'). Fold them to a
# space on both sides so they can't cause false FAILs.
_DASH_CHARS = {
    "\u00ad",  # soft hyphen
    "\u2010",  # hyphen
    "\u2011",  # non-breaking hyphen
    "\u2012",  # figure dash
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\u2015",  # horizontal bar
    "\u2212",  # minus sign
}


def _normalize(text: str) -> str:
    """Fold hyphen variants to spaces: 'double‐width' -> 'double width'."""
    return "".join(" " if ch in _DASH_CHARS else ch for ch in text)


def keyword_score(answer: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """PASS when every keyword appears in the answer (case-insensitive).

    Hyphen variants in both the answer and the keyword are folded to spaces
    before matching, so:
      - keyword 'double-width'  matches answer 'double‑width' (NB hyphen)
      - keyword 'square-brackets' matches answer 'square‑brackets'
      - keyword 'square brackets' also matches 'square‑brackets'
    """
    lowered = _normalize(answer.lower())
    # Fold hyphens in keywords to spaces too, so a keyword like 'double-width'
    # can match when the model writes 'double‑width' (which normalizes to 'double width').
    missing = [
        k
        for k in keywords
        if _normalize(k.lower()).replace("-", " ") not in lowered
    ]
    return (not missing, missing)


def evaluate(orchestrator, evals: list[dict]) -> tuple[list[dict], int]:
    results = []
    passed = 0

    for ev in evals:
        print(f"\n--- {ev['id']} ---")
        print(f"Q: {ev['question']}")

        try:
            result = orchestrator.ask(ev["question"])
            answer = result.answer
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            results.append(
                {
                    "user_input": ev["question"],
                    "response": "",
                    "retrieved_contexts": [],
                    "reference": ev["expected_answer"],
                    "crag_verdict": None,
                }
            )
            continue

        ok, missing = keyword_score(answer, ev.get("keywords", []))
        passed += ok

        print("PASS" if ok else f"FAIL — missing keywords: {missing}")
        print(f"A: {answer[:400]}")
        sources = [
            f"{c.file_path}:{c.node_type} '{c.name}' (lines {c.start_line}-{c.end_line})"
            for c in result.retrieved_chunks
        ]
        print(f"Sources: {', '.join(sources) if sources else '(none)'}")
        verdict = getattr(result, "verdict", None)
        if verdict:
            trace = f"  CRAG: verdict={verdict}, rounds={getattr(result, 'corrective_rounds', 0)}"
            rewritten = getattr(result, "rewritten_query", None)
            refinement = getattr(result, "refinement", None)
            if rewritten:
                trace += f", rewritten={rewritten!r}"
            if refinement:
                trace += f", {refinement}"
            print(trace)

        results.append(
            {
                "user_input": ev["question"],
                "response": answer,
                "retrieved_contexts": [c.text for c in result.retrieved_chunks],
                "reference": ev["expected_answer"],
                "crag_verdict": verdict,
            }
        )

    return results, passed


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and CRASH printing exotic model output
    # (e.g. U+202F narrow no-break space) — replace instead of raising.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Run the golden eval dataset through the RAG pipeline.")
    parser.add_argument("--collection", default="code_chunks")
    parser.add_argument("--qdrant-dir", default="qdrant_data")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--no-crag", action="store_true")
    args = parser.parse_args(argv)

    orchestrator = build_orchestrator(
        qdrant_dir=args.qdrant_dir,
        collection=args.collection,
        model=args.model,
        top_k=args.top_k,
        rerank=not args.no_rerank,
        candidate_k=args.candidate_k,
        min_score=args.min_score,
        crag=not args.no_crag,
    )

    evals = load_evals()
    if not evals:
        print(f"No eval entries found in {EVALS_FILE}.")
        return 1

    results, passed = evaluate(orchestrator, evals)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 50}")
    print(f"SCORE: {passed}/{len(results)} passed")
    print(f"Details written to {RESULTS_FILE}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
