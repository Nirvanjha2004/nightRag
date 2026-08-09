# Issue 05 — Uncapped `retry-after` backoff stalled the eval 16+ min on one question

**Date:** 2026-08-09
**Status:** RESOLVED (2026-08-09)
**Component:** `app/generator.py` (`_backoff_seconds`)
**Severity:** high (run appeared hung)

## Symptom
The eval run sat on E07 for 16+ minutes: log stopped advancing, the process
showed ~zero CPU (blocked in `time.sleep`), no error ever surfaced. The question
was mid-corrective-round with several Groq calls queued behind rate limits.

## Where it appeared
First full `run_evals.py` attempt with the reranker actually burning tokens
(issue 03 fix) — real token usage tripped Groq's free-tier TPM limit, and the
retry loop then stalled.

## Root cause
`_backoff_seconds` honored the server's `retry-after` header **verbatim, uncapped**:
a large hint (e.g. a daily-reset value) made the retry loop sleep for hours per
attempt, while the 8k-TPM window actually refills in ~60s. The 60s
`_MAX_BACKOFF_SECONDS` cap only applied to the exponential fallback, not the
header branch.

## Fix / workaround
- Cap the `retry-after` sleep at `_MAX_BACKOFF_SECONDS` (60s) — the loop now
  retries at most ~5 min per call before surfacing the error (callers degrade
  gracefully: reranker → base order, CRAG → plain RAG, eval → ERROR row).
- Added a 120s client `timeout` to the Groq client so a genuinely dead request
  can't hang the pipeline either.
- Expect eval runs to be TPM-paced (~20–40 min for 20 questions) — that's
  normal, not a hang.

## Related
- `test_pipeline.py` regression guard: asserts `_backoff_seconds` caps a
  `retry-after: 3600` hint at 60.0 and still honors small hints (3s → 3.0)
- issue 04 (unicode crash) — same failed first run
