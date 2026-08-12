"""
sources.py — turn "what the user wants ingested" into "a directory on disk".

Three ways in, one way out (a temporary or existing directory that ingestion can
walk):

    path   — a directory already on the server's filesystem
    git    — a shallow clone of a public repository
    upload — a .zip the user dropped into the browser

Everything here runs on user-supplied input, so each resolver validates before
it touches the filesystem or spawns a process.
"""

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# A shallow clone of a normal repo finishes well inside this; a hung network
# call must not pin a worker thread forever.
GIT_CLONE_TIMEOUT_SECONDS = 300

_ALLOWED_GIT_SCHEMES = ("https://", "http://", "git://", "ssh://", "git@")


class SourceError(ValueError):
    """The requested source is unusable, with a message meant for the user."""


def resolve_path(raw: str) -> Path:
    """Validate a server-side directory path."""
    path = Path(os.path.expanduser(raw.strip())).resolve()
    if not path.exists():
        raise SourceError(f"Path not found: {path}")
    if not path.is_dir():
        raise SourceError(f"Not a directory: {path}")
    return path


@contextmanager
def clone_repo(url: str) -> Iterator[Path]:
    """Shallow-clone `url` into a temp dir; remove it on the way out."""
    url = url.strip()
    if not url.startswith(_ALLOWED_GIT_SCHEMES):
        raise SourceError(
            "Repository URL must start with https://, http://, git://, ssh:// or git@."
        )
    # A URL that reads as a flag would otherwise be handed to git as one.
    if url.startswith("-"):
        raise SourceError("Invalid repository URL.")
    if shutil.which("git") is None:
        raise SourceError("git is not installed on the server, so cloning is unavailable.")

    workdir = Path(tempfile.mkdtemp(prefix="nightrag-clone-"))
    target = workdir / "repo"
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", "--", url, str(target)],
            capture_output=True,
            text=True,
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
            # No credential prompt: a private URL should fail fast, not hang a
            # worker thread waiting on stdin nobody can type into.
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise SourceError("git clone failed: " + (detail[-1] if detail else "unknown error"))
        yield target
    except subprocess.TimeoutExpired:
        raise SourceError("git clone timed out.")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@contextmanager
def extract_zip(data: bytes, filename: str) -> Iterator[Path]:
    """Extract an uploaded .zip into a temp dir; remove it on the way out.

    Entries that would escape the destination (absolute paths, ``..`` segments,
    symlinks) are skipped rather than written — a zip is untrusted input, and
    "zip slip" writes outside the extraction root.
    """
    workdir = Path(tempfile.mkdtemp(prefix="nightrag-zip-"))
    target = workdir / "repo"
    target.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = target.resolve()
            for member in archive.infolist():
                if member.is_dir():
                    continue
                destination = (target / member.filename).resolve()
                if not str(destination).startswith(str(root) + os.sep):
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(destination, "wb") as sink:
                    shutil.copyfileobj(source, sink)
    except zipfile.BadZipFile:
        shutil.rmtree(workdir, ignore_errors=True)
        raise SourceError(f"{filename} is not a valid .zip archive.")
    except SourceError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    try:
        yield _unwrap_single_root(target)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _unwrap_single_root(directory: Path) -> Path:
    """GitHub zips wrap everything in one `repo-main/` folder — step into it."""
    entries = list(directory.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return directory
