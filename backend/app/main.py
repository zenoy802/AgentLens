import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import api_router
from app.core.config import get_settings
from app.core.errors import NotFoundError, register_exception_handlers
from app.core.logging import setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.db.session import dispose_engine, initialize_metadata_database

API_PREFIX = "/api/v1"
API_PATH_PREFIX = API_PREFIX.lstrip("/")


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    raw_paths = schema.get("paths")
    if isinstance(raw_paths, dict):
        schema["paths"] = {
            path.removeprefix(API_PREFIX) or "/": value
            for path, value in raw_paths.items()
            if isinstance(path, str)
        }
    schema["servers"] = [{"url": API_PREFIX}]
    app.openapi_schema = schema
    return schema


def _default_static_dir() -> Path:
    app_static_dir = Path(__file__).parent / "static"
    if app_static_dir.exists():
        return app_static_dir
    return Path.cwd() / "static"


def mount_static_frontend(app: FastAPI, static_dir: Path | None = None) -> None:
    resolved_static_dir = (static_dir or _default_static_dir()).resolve()
    index_path = resolved_static_dir / "index.html"
    if not index_path.is_file():
        return

    assets_dir = resolved_static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa_or_static_file(full_path: str) -> FileResponse:
        if full_path == API_PATH_PREFIX or full_path.startswith(f"{API_PATH_PREFIX}/"):
            raise NotFoundError()

        requested_path = (resolved_static_dir / full_path).resolve()
        if _path_is_relative_to(requested_path, resolved_static_dir) and requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(index_path)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        startup_started = time.perf_counter()
        settings.ensure_directories()
        setup_logging()
        logger.info(
            "AgentLens Backend starting...\n"
            "  data dir: {}\n"
            "  metadata db: {}\n"
            "  host: {} port: {}\n"
            "  cleanup scheduler: enabled (daily 03:00)",
            settings.data_dir,
            settings.metadata_db_path,
            settings.host,
            settings.port,
        )
        initialize_metadata_database()
        logger.info("Database schema up to date.")
        scheduler = start_scheduler(settings)
        app.state.scheduler = scheduler
        app.state.started_at = time.monotonic()
        startup_ms = int((time.perf_counter() - startup_started) * 1000)
        logger.info("Startup complete in {} ms.", startup_ms)
        yield
        shutdown_scheduler(getattr(app.state, "scheduler", None))
        dispose_engine()

    app = FastAPI(
        title="AgentLens API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    def custom_openapi() -> dict[str, Any]:
        return _build_openapi_schema(app)

    cast(Any, app).openapi = custom_openapi
    app.state.started_at = time.monotonic()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=API_PREFIX)
    register_exception_handlers(app)
    mount_static_frontend(app)
    return app


app = create_app()
