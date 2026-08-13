# Issue NN — <short title>

**Date:** YYYY-MM-DD
**Status:** OPEN | RESOLVED (add resolution date)
**Component:** which file / command / model (e.g. `app/llm_reranker.py`, `run_ragas.py`, Ollama `qwen2.5:3b`, Groq `openai/gpt-oss-120b`)
**Severity:** low | medium | high | blocker

## Symptom
What did you actually see? Paste the error line, the trace, the score, the
hang. (e.g. `UnicodeEncodeError: 'charmap' codec can't encode character '\u202f'`)

## Where it appeared
Which command / question / eval row? (`python run_evals.py` on E19, `python run_ragas.py`, a one-shot `main.py` query, …)

## Root cause
What was actually going on, once you figured it out. (e.g. gpt-oss-120b is a
reasoning model and its hidden reasoning consumed the whole 256-token cap → empty output)

## Fix / workaround
What fixed it (or what unblocks it meanwhile). Link the code change / commit if there is one.

## Related
- journey run / scoreboard entry
- test that guards against regression (if any)
