"""FastAPI application entry point: builds and configures the app, registers route routers, and starts the dev server."""

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
    """Start one background sweep, if enabled. A sweep that cannot start must never stop the API serving."""
    if not enabled:
        _logger.info("%s disabled by configuration", label.capitalize())
        return

    try:
        start()
    except Exception:
        _logger.exception("Could not start the %s", label)


def _stop_sweep(label: str, stop: Callable[[], None]) -> None:
    """Stop one background sweep, whatever state it is in - shutdown must still finish."""
    try:
        stop()
    except Exception:
        _logger.exception("Could not stop the %s cleanly", label)


def _reset_interrupted_jobs() -> None:
    """Fail any job left active by a previous process run. A startup task, not a sweep."""
    try:
        job_runner.reset_interrupted_jobs(JobRepository())
    except Exception:
        _logger.exception("Could not reset interrupted jobs on startup")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    configure_logging()
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Run startup tasks and the app's background sweeps for as long as it is serving.

        Job execution now lives entirely in this process's memory (see
        services/job_runner.py), so a job left 'queued'/'running'/'cancelling'
        when the process last stopped was abandoned mid-run, not paused -
        reset_interrupted_jobs() fails those explicitly once, here, rather than
        leaving them to sit forever. There is no ongoing reconciliation sweep to
        run alongside it: with one process owning a job start to finish, there is
        nothing left to ask.

        The notification retention sweep deletes read notifications past their
        window - see services/notification_retention.py. It needs no lock: its
        deletes are row-locked in batches, so concurrent sweeps take different rows.

        Opt out with RUN_NOTIFICATION_PURGE=false, e.g. for a one-off task
        container running migrations, which has no business deleting data.
        """
        _reset_interrupted_jobs()
        _start_sweep("notification retention sweep", RUN_NOTIFICATION_PURGE, notification_retention.start)

        try:
            yield
        finally:
            _stop_sweep("notification retention sweep", notification_retention.stop)

    app = FastAPI(title="DUSTER", lifespan=lifespan)

    @app.middleware("http")
    async def reject_oversized_uploads(request: Request, call_next):
        """Reject POST /api/upload requests larger than the configured size limit."""

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
        """Log each request's method/path/status, and turn an unhandled exception into a JSON response.

        Returning a response here (rather than letting the exception
        propagate to Starlette's default handler) matters for CORS:
        CORSMiddleware is registered outside this middleware, so it only
        gets to add Access-Control-* headers to a Response this layer
        actually returns - an exception that escapes past here instead
        reaches Starlette's outermost error handler, which sits *outside*
        CORSMiddleware and produces a response with no CORS headers at all.
        The browser then reports that as a CORS failure ("No
        'Access-Control-Allow-Origin' header") instead of showing the real
        error - most confusing on POST /api/auth/login, the one request
        every user makes on first load.
        """

        # Bound before anything else runs, so every log line emitted while
        # handling this request - including from repositories and connectors
        # several layers down - carries the same id. An inbound X-Request-ID is
        # honoured so a value assigned by a load balancer or by the caller
        # stitches together with ours rather than competing with it.
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

        # Handed back so a user reporting a problem can quote it, and so the id
        # in their browser's network tab matches the one in the server log.
        response.headers["X-Request-ID"] = request_id

        # Duration is logged for every request, which is what makes "the app is
        # slow" answerable without adding a metrics backend first.
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

    # health and auth itself stay open; every other router requires a valid
    # session. Registering a future router the same way protects it too -
    # nothing page-specific to remember.
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

    # The one deliberate exception to "every router gets protected_dependencies":
    # require_auth slides the session forward on each call, and a stream that stays
    # open would then keep an idle session alive forever. The stream authenticates
    # itself with require_auth_no_slide, and test_auth_gate.py keeps it honest.
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
