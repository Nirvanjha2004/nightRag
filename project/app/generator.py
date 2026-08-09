"""
generator.py — pure LLM call wrapper. No prompt-building logic, no retrieval logic here.
Takes a finished prompt string, returns the generated answer text.
"""

import time

from groq import Groq, APIStatusError

# Groq reports per-minute token/request limits as HTTP 429, and also as 413
# with code 'rate_limit_exceeded' ("Request too large ... on tokens per minute").
_RETRYABLE_STATUS_CODES = frozenset({413, 429})

# Backoff cap: Groq's TPM window is ~60s, so sleeping longer just wastes time.
_MAX_BACKOFF_SECONDS = 60.0


def _is_rate_limit_error(error: APIStatusError) -> bool:
    """True for 429/413 rate-limit responses, False for genuine client errors."""
    if error.status_code in _RETRYABLE_STATUS_CODES:
        return True
    body = error.body if isinstance(error.body, dict) else {}
    err = body.get("error", {}) if isinstance(body.get("error"), dict) else {}
    return err.get("code") == "rate_limit_exceeded" or err.get("type") == "tokens"


def _backoff_seconds(error: APIStatusError, attempt: int) -> float:
    """Prefer the server's Retry-After hint; otherwise exponential backoff.

    Either way the sleep is capped at _MAX_BACKOFF_SECONDS: Groq's TPM window
    refills within a minute, so honoring a huge retry-after hint (e.g. a daily
    reset) would stall the pipeline for hours over a limit that resets sooner.
    """
    retry_after = error.response.headers.get("retry-after")
    if retry_after:
        try:
            return min(_MAX_BACKOFF_SECONDS, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(_MAX_BACKOFF_SECONDS, 2.0 ** attempt)


class Generator:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        max_retries: int = 5,
        timeout: float = 120.0,
    ):
        # timeout guards against a hung request stalling the whole pipeline
        # (a rate-limited call retries with backoff instead; a genuinely dead
        # connection raises and the caller's degradation path kicks in).
        self.client = Groq(api_key=api_key, timeout=timeout)
        self.model = model
        self.max_retries = max_retries

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """Send the prompt to Groq and return the generated answer text.

        Args:
            prompt: the user message content.
            system_prompt: optional system-role instructions, sent as a
                separate ``system`` message ahead of the user message
                (chat-tuned models weight ``system`` instructions more heavily
                than ones buried inside the user message).
            temperature: kept low (0.1) by default since this is a factual,
                context-grounded RAG answer, not creative generation — reduces
                the chance of the model drifting from the provided context.
            max_tokens: cap on generated tokens.

        Rate-limit responses (429, and 413 with code 'rate_limit_exceeded') are
        retried with backoff: the free tier's 8k TPM window refills within a
        minute, so a transient rejection succeeds on retry. Genuine client
        errors (400, 404, ...) propagate immediately.
        """

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content   
            except APIStatusError as error:
                if not _is_rate_limit_error(error):
                    raise
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(_backoff_seconds(error, attempt))

        raise RuntimeError("unreachable")  # loop always returns or raises
