"""Small data utilities: JSON loading, paragraph-aware text chunking, and a
token-bucket rate limiter.
"""

import json
import time
from pathlib import Path


def load_json(path: str) -> dict:
    """Load a UTF-8 JSON file and return it as a dict.

    Raises TypeError if the top-level value is not a JSON object.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Expected a JSON object at the top level")
    return data


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Split `text` into chunks on paragraph boundaries.

    Paragraphs are separated by blank lines. A paragraph longer than
    max_chars is hard-split (no word-boundary preservation). Raises
    ValueError if max_chars is not positive.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(para) > max_chars:
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        current = para

    if current:
        chunks.append(current)
    return chunks


class TokenBucket:
    """Classic token bucket: tokens accrue at `refill_rate` per second, up to
    `capacity`. try_acquire() returns True only when enough tokens are present.
    """

    def __init__(self, capacity: float, refill_rate: float):
        if capacity <= 0 or refill_rate <= 0:
            raise ValueError("capacity and refill_rate must be positive")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Consume `tokens` if available; returns False otherwise."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
