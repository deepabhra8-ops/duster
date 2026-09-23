from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from core.config import NOTIFICATION_STREAM_POLL_SECONDS, SESSION_COOKIE_NAME
from repositories.notification_repository import notification_repository
from routes.auth_routes import require_auth, require_auth_no_slide
from services.notification_service import (
    DEFAULT_PAGE_SIZE,
    NotificationPermissionError,
    NotificationValidationError,
    notification_service,
)
from services.notification_stream import HEARTBEAT_SECONDS, notification_event_stream
from utils.logger import get_logger


logger = get_logger(__name__)


notification_bp = APIRouter()
notification_stream_bp = APIRouter()


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


def _parse_id(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


async def _json_body(request: Request) -> dict | None:
    try:
        body = await request.json()
    except ValueError:
        return None

    return body if isinstance(body, dict) else None


@notification_bp.get("/api/notifications")
def list_notifications(request: Request, username: str = Depends(require_auth)):
    params = request.query_params

    try:
        limit = int(params.get("limit", DEFAULT_PAGE_SIZE))
        before = int(params["before"]) if params.get("before") else None
    except ValueError:
        return _error("limit and before must be integers", 400)

    if limit < 1:
        return _error("limit must be at least 1", 400)

    if before is not None and before < 1:
        return _error("before must be a positive id", 400)

    unread_only = params.get("unread", "").strip().lower() in ("1", "true", "yes")

    try:
        return {
            "ok": True,
            "data": notification_service.list_for(username, limit, before, unread_only),
        }
    except Exception:
        logger.exception("Failed to list notifications")
        return _error("Failed to load notifications", 500)


@notification_bp.post("/api/notifications")
async def create_notification(request: Request, username: str = Depends(require_auth)):
    body = await _json_body(request)

    if body is None:
        return _error("Request body must be a JSON object", 400)

    try:
        notification = await run_in_threadpool(
            lambda: notification_service.create(
                username,
                type=body.get("type"),
                title=body.get("title"),
                content=body.get("content", ""),
                link=body.get("link"),
                username=body.get("username"),
            )
        )
    except NotificationValidationError as exc:
        return _error(str(exc), 400)
    except NotificationPermissionError as exc:
        return _error(str(exc), 403)
    except Exception:
        logger.exception("Failed to create a notification")
        return _error("Failed to create the notification", 500)

    return JSONResponse({"ok": True, "data": notification}, status_code=201)


@notification_bp.post("/api/notifications/read-all")
def mark_all_notifications_read(username: str = Depends(require_auth)):
    try:
        return {"ok": True, "data": notification_service.mark_all_read(username)}
    except Exception:
        logger.exception("Failed to mark all notifications read")
        return _error("Failed to update notifications", 500)


@notification_bp.delete("/api/notifications")
def clear_notifications(username: str = Depends(require_auth)):
    try:
        return {"ok": True, "data": notification_service.clear_all(username)}
    except Exception:
        logger.exception("Failed to clear notifications")
        return _error("Failed to clear notifications", 500)


@notification_bp.patch("/api/notifications/{notification_id}")
async def update_notification(
    notification_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    parsed_id = _parse_id(notification_id)

    if parsed_id is None:
        return _error("Notification not found", 404)

    body = await _json_body(request)

    if body is None or body.get("status") != "read":
        return _error('Only {"status": "read"} is supported', 400)

    try:
        result = await run_in_threadpool(notification_service.mark_read, username, parsed_id)
    except Exception:
        logger.exception("Failed to mark notification %s read", parsed_id)
        return _error("Failed to update the notification", 500)

    if result is None:
        return _error("Notification not found", 404)

    return {"ok": True, "data": result}


@notification_stream_bp.get("/api/notifications/stream")
async def stream_notifications(
    request: Request,
    username: str = Depends(require_auth_no_slide),
):
    try:
        after_id = await run_in_threadpool(notification_repository.latest_id, username)
    except Exception:
        logger.exception("Failed to open the notification stream")
        return _error("Failed to open the notification stream", 500)

    return StreamingResponse(
        notification_event_stream(
            username,
            request.cookies.get(SESSION_COOKIE_NAME),
            after_id=after_id,
            poll_seconds=NOTIFICATION_STREAM_POLL_SECONDS,
            heartbeat_seconds=HEARTBEAT_SECONDS,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
