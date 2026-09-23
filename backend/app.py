import time
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routes.dashboard_routes import dashboard_bp
from routes.metadata_routes import metadata_bp

from core.storage_layout import ensure_directories
from core.config import (
    ALLOWED_ORIGINS,
    DEBUG,
    HOST,
    MAX_UPLOAD_SIZE_BYTES,
    RUN_NOTIFICATION_PURGE,
    PORT,
    THREADED,
)

from routes.health_routes import health_bp
from routes.auth_routes import auth_bp, require_auth
from routes.connection_routes import connection_bp
from routes.upload_routes import upload_bp
from routes.job_routes import job_bp
from routes.download_routes import download_bp
from routes.lov_routes import lov_bp
from routes.notification_routes import notification_bp, notification_stream_bp
from repositories.job_repository import JobRepository
from services import job_runner
from services.notification_retention import notification_retention
from utils.logger import configure_logging, get_logger, new_request_id, set_request_id


_logger = get_logger(__name__)


def _start_sweep(label: str, enabled: bool, start: Callable[[], None]) -> None:
    if not enabled:
        _logger.info("%s disabled by configuration", label.capitalize())
        return

    try:
        start()
    except Exception:
        _logger.exception("Could not start the %s", label)


def _stop_sweep(label: str, stop: Callable[[], None]) -> None:
    try:
        stop()
    except Exception:
        _logger.exception("Could not stop the %s cleanly", label)


def _reset_interrupted_jobs() -> None:
    try:
        job_runner.reset_interrupted_jobs(JobRepository())
    except Exception:
        _logger.exception("Could not reset interrupted jobs on startup")


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _reset_interrupted_jobs()
        _start_sweep("notification retention sweep", RUN_NOTIFICATION_PURGE, notification_retention.start)

        try:
            yield
        finally:
            _stop_sweep("notification retention sweep", notification_retention.stop)

    app = FastAPI(title="DUSTER", lifespan=lifespan)

    @app.middleware("http")
    async def reject_oversized_uploads(request: Request, call_next):
        content_length = request.headers.get("content-length")

        if (
            request.method == "POST"
            and request.url.path == "/api/upload"
            and content_length
            and int(content_length) > MAX_UPLOAD_SIZE_BYTES
        ):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Upload exceeds the 200 MB limit",
                },
                status_code=413,
            )

        return await call_next(request)

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_request_id()
        set_request_id(request_id)

        started = time.perf_counter()

        logger.info(
            "Request started: %s %s",
            request.method,
            request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled exception while processing %s %s after %.0fms",
                request.method,
                request.url.path,
                (time.perf_counter() - started) * 1000,
            )
            return JSONResponse(
                {"ok": False, "error": "Internal server error"},
                status_code=500,
                headers={"X-Request-ID": request_id},
            )

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "Request completed: %s %s -> %s in %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ensure_directories()

    app.include_router(health_bp)
    app.include_router(auth_bp)
    protected_dependencies = [Depends(require_auth)]
    app.include_router(connection_bp, dependencies=protected_dependencies)
    app.include_router(upload_bp, dependencies=protected_dependencies)
    app.include_router(job_bp, dependencies=protected_dependencies)
    app.include_router(download_bp, dependencies=protected_dependencies)
    app.include_router(metadata_bp, dependencies=protected_dependencies)
    app.include_router(dashboard_bp, dependencies=protected_dependencies)
    app.include_router(lov_bp, dependencies=protected_dependencies)
    app.include_router(notification_bp, dependencies=protected_dependencies)

    app.include_router(notification_stream_bp)

    logger.info("Application initialized")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
