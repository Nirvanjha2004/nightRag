"""
app.py — the FastAPI application.

One process serves both halves of NightRag:

    /api/*   the pipeline (ask, ingest, collections)
    /*       the built React UI from web/dist, when it exists

Serving the UI from the same origin is what makes the whole thing a single
command for a user who just wants to run it (`npm run build`, then
`python run_server.py`). During development the Vite dev server proxies /api
here instead, so both halves hot-reload.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from server.engine import RagEngine
from server.jobs import JobRegistry
from server.routes import router
from server.settings import Settings, load_settings

DESCRIPTION = """\
Ask questions about a Python codebase. Retrieval is hybrid (BM25 + dense,
RRF-fused), re-ranked by an LLM, and self-corrected before the answer is
generated.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The embedded Qdrant client is opened lazily on first use, and released
        # here so a restart is never blocked by a stale storage lock.
        yield
        app.state.engine.close()

    app = FastAPI(
        title="NightRag",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = RagEngine(settings)
    app.state.jobs = JobRegistry()

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc: StarletteHTTPException):
        # One error shape everywhere, so the UI never has to guess whether a
        # failure arrived as {detail} or {message}.
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status": exc.status_code},
        )

    _mount_web_ui(app, settings)
    return app


def _mount_web_ui(app: FastAPI, settings: Settings) -> None:
    """Serve the built SPA at / — silently skipped when it has not been built."""
    dist = settings.web_dist
    index = dist / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        async def missing_ui() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "The web UI has not been built yet.",
                    "hint": "cd web && npm install && npm run build — or run `npm run dev` "
                            "for the dev server.",
                    "api_docs": "/docs",
                },
            )
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """Any non-/api path resolves to a real file, or to index.html.

        Client-side routes (/corpus, /settings) have no file behind them, so
        they fall through to the SPA shell and React resolves them. API paths
        never do: an unknown endpoint must 404, not quietly return HTML that a
        fetch() would then fail to parse.
        """
        if full_path.startswith("api/"):
            raise StarletteHTTPException(status_code=404, detail=f"No such endpoint: /{full_path}")

        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(dist.resolve())):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
