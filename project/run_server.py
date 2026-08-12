"""
run_server.py — start the NightRag API + web UI.

    python run_server.py                 # http://127.0.0.1:8000
    python run_server.py --port 9000
    python run_server.py --reload         # auto-restart on code changes (dev)

Configuration comes from .env / the environment (see server/settings.py and
.env.example); the flags here only override the network binding.

Note on --reload: the embedded Qdrant store allows exactly one process to hold
its directory. The reloader replaces the worker on each change, so a save while
a request is in flight can briefly collide — use it for UI/API work, not while
running long ingestions.
"""

import argparse
import sys

import uvicorn

from server.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and crash printing exotic characters.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    settings = load_settings()

    parser = argparse.ArgumentParser(
        prog="python run_server.py",
        description="Serve the NightRag API and web UI.",
    )
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true", help="Restart on code changes (dev)")
    args = parser.parse_args(argv)

    missing = settings.missing_keys()
    if missing:
        print(f"[warning] Missing API key(s): {', '.join(missing)}.")
        print("          The server will start, but questions will fail until you")
        print("          add them to .env (see .env.example) and restart.")

    if not (settings.web_dist / "index.html").is_file():
        print(f"[note] No built UI at {settings.web_dist}. The API works; for the UI run:")
        print("       cd web && npm install && npm run build")

    print(f"NightRag on http://{args.host}:{args.port}  (API docs at /docs)")
    print(f"Storage: {settings.qdrant_url or f'embedded {settings.qdrant_dir}'}")

    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
