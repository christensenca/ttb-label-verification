"""FastAPI application entrypoint.

Wires:
- CORS middleware from `CORS_ALLOWED_ORIGINS`
- `Cache-Control: no-store` on all `/api/*` responses
- `/healthz` liveness + DB reachability probe
- `/openapi.json` & Swagger UI
- Static SPA mount at `/` with non-`/api/*` SPA fallback (when the build exists)
- Lifespan: startup rescue + idempotent fixture seed
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env into os.environ so pipeline.extract (which reads os.environ
# directly per the tolerated deviation in plan.md) sees OPENROUTER_API_KEY.
load_dotenv()

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

# Uvicorn's default logging config only attaches handlers to `uvicorn.*`
# loggers; ours (`app.*`, `ttb.processor.event`) would otherwise drop to
# stderr via the last-resort handler at WARNING. Configure a minimal root
# handler so INFO from our code — including the per-item extraction event
# line (T083) — actually reaches stdout for cloud-log scraping.
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

from app.api import admin as admin_api
from app.api import decisions as decisions_api
from app.api import overrides as overrides_api
from app.api import submissions as submissions_api
from app.config import get_settings
from app.db.seed import run_seed
from app.db.session import engine
from app.services.processor import rescue_processing_on_startup

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """App startup: rescue interrupted processing rows, then idempotent seed."""
    try:
        rescued = rescue_processing_on_startup()
        if rescued:
            logger.info("startup: rescued %d processing submissions", rescued)
        run_seed()
    except Exception:
        logger.exception("startup: lifespan initialization failed")
        raise
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="TTB Label Verify",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _api_no_store(request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(submissions_api.router)
    app.include_router(decisions_api.router)
    app.include_router(overrides_api.router)
    app.include_router(admin_api.router)

    @app.get("/healthz", tags=["health"])
    def healthz() -> Response:
        # Liveness is implicit (this function ran). DB reachability requires
        # a real round-trip — Railway/Azure can be "alive" while the database
        # is unreachable, and that is exactly the case we want to surface.
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - exercised by ops, not tests
            return JSONResponse(
                {"status": "error", "alive": True, "database": "error", "detail": str(exc)},
                status_code=500,
            )
        return JSONResponse({"status": "ok", "alive": True, "database": "ok"})

    # Static SPA mount. In dev (before `pnpm build`) the dist dir doesn't exist;
    # skip the mount so the API is still usable on its own.
    if FRONTEND_DIST.is_dir():
        _mount_spa(app, FRONTEND_DIST)

    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve frontend/dist at `/`, with SPA fallback to index.html.

    Order matters — declare the catch-all *before* mounting StaticFiles so
    `/api/*` and `/healthz` routes already registered keep priority. Only paths
    that do NOT match a registered route reach the fallback.
    """
    index_html = dist / "index.html"
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def _root() -> FileResponse:
        return FileResponse(index_html)

    # Catch-all for SPA routes. FastAPI matches more-specific routes first;
    # /api/* and /healthz are already declared.
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/") or full_path == "healthz":
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_html)


app = create_app()
