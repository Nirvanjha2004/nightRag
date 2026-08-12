"""
settings.py — everything the server reads from the environment, in one object.

Key names are the ones the CLI has always used (`jina_api_key`, `groq_api_key`
in .env), with SCREAMING_CASE aliases so Docker/CI users can set them the way
they expect. Nothing here reaches out to the network or opens a database — it
is pure configuration, so it can be imported by tests.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config import load_env
from app.factory import DEFAULT_COLLECTION, DEFAULT_MODEL


def _env(*names: str, default: str = "") -> str:
    """First non-empty value among `names`, else `default`."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class Settings:
    jina_api_key: str = ""
    groq_api_key: str = ""

    # Storage: an embedded Qdrant directory owned by this process, or a URL of
    # a Qdrant server shared with other processes (e.g. Qdrant Cloud).
    qdrant_dir: str = "qdrant_data"
    qdrant_url: str | None = None
    qdrant_api_key: str = ""  # required by hosted Qdrant (Qdrant Cloud)

    default_collection: str = DEFAULT_COLLECTION
    default_model: str = DEFAULT_MODEL

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=list)

    # Ingesting from a server-side path reads the machine the server runs on.
    # That is exactly right for the local dev tool this is, and exactly wrong
    # for a shared deployment — hence the switch.
    allow_local_path: bool = True
    allow_git_clone: bool = True
    max_upload_mb: int = 64

    # Built SPA. Served at / when present, so `python run_server.py` is the
    # only command a user needs after `npm run build`.
    web_dist: Path = Path("web/dist")

    @property
    def has_keys(self) -> bool:
        return bool(self.jina_api_key and self.groq_api_key)

    def missing_keys(self) -> list[str]:
        missing = []
        if not self.jina_api_key:
            missing.append("jina_api_key")
        if not self.groq_api_key:
            missing.append("groq_api_key")
        return missing


def load_settings(env_file: str = ".env") -> Settings:
    """Read .env (without clobbering real env vars), then build Settings."""
    load_env(env_file)

    origins = _env("NIGHTRAG_CORS_ORIGINS")
    qdrant_url = _env("NIGHTRAG_QDRANT_URL", "QDRANT_URL")

    return Settings(
        jina_api_key=_env("jina_api_key", "JINA_API_KEY"),
        groq_api_key=_env("groq_api_key", "GROQ_API_KEY"),
        qdrant_dir=_env("NIGHTRAG_QDRANT_DIR", "QDRANT_DIR", default="qdrant_data"),
        qdrant_url=qdrant_url or None,
        qdrant_api_key=_env("NIGHTRAG_QDRANT_API_KEY", "QDRANT_API_KEY"),
        default_collection=_env("NIGHTRAG_COLLECTION", default=DEFAULT_COLLECTION),
        default_model=_env("NIGHTRAG_MODEL", "GROQ_MODEL", default=DEFAULT_MODEL),
        host=_env("NIGHTRAG_HOST", default="127.0.0.1"),
        # PORT is the convention every PaaS (Render, Heroku, Fly) injects, so
        # NIGHTRAG_PORT wins when set and plain `PORT` is the platform default.
        port=_env_int("NIGHTRAG_PORT", _env_int("PORT", 8000)),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_local_path=_env_bool("NIGHTRAG_ALLOW_LOCAL_PATH", True),
        allow_git_clone=_env_bool("NIGHTRAG_ALLOW_GIT_CLONE", True),
        max_upload_mb=_env_int("NIGHTRAG_MAX_UPLOAD_MB", 64),
        web_dist=Path(_env("NIGHTRAG_WEB_DIST", default="web/dist")),
    )
