"""
config.py — tiny, dependency-free .env loader.

Loads KEY=VALUE pairs from a .env file into os.environ (without overwriting
keys that are already set in the real environment). Handles blank lines,
# comments, and surrounding quotes.

Shared by app/ingestion.py, main.py and run_evals.py so the API keys live in
one place (.env) and are read the same way everywhere.
"""

import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE lines from `path` into os.environ if not already set."""
    env_path = Path(path)
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value
