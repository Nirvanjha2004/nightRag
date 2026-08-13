# Issue 04 — Windows console crash on exotic Unicode in model answers

**Date:** 2026-08-09
**Status:** RESOLVED (2026-08-09)
**Component:** `run_evals.py`, `main.py`, `run_ragas.py` (console printing)
**Severity:** medium (crashed a whole eval run)

## Symptom
`run_evals.py` died mid-run with:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u202f' in position 150: character maps to <undefined>
```

at the `print(f"A: {answer[:400]}")` line — the model's answer contained a
U+202F narrow no-break space (copied from the source code being analyzed).

## Where it appeared
`python run_evals.py` on E02, Windows console (cp1252 default encoding).

## Root cause
Windows consoles default to cp1252; exotic characters in model output can't be
encoded and Python raises instead of printing. The char came from the `rich`
source itself, so it's not a one-off — it re-appears whenever the model quotes
that code.

## Fix / workaround
`sys.stdout.reconfigure(errors="replace")` at the top of `main()` in
`run_evals.py`, `main.py`, and `run_ragas.py` — unencodable chars print as `?`
instead of crashing. The JSONL artifacts are written with explicit
`encoding="utf-8"` so no data is lost.

## Related
- issue 05 (rate-limit stall) — both found while trying to run the first CRAG eval
