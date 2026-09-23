"""HTTP endpoints for the top bar's notification bell.

    GET    /api/notifications          the signed-in user's notifications, newest first
    POST   /api/notifications          create one (for yourself; admins may name another user)
    PATCH  /api/notifications/{id}     mark one read
    POST   /api/notifications/read-all mark all read
    DELETE /api/notifications          delete all of the user's notifications (irreversible)
    GET    /api/notifications/stream   live feed of new notifications (Server-Sent Events)

Everything is scoped to the authenticated user: a notification that belongs to
someone else is reported as not found, the same as one that does not exist.

Two routers, on purpose. `notification_bp` is registered in create_app() with the
usual Depends(require_auth). The stream lives on `notification_stream_bp`, which
is not - require_auth slides the session's expiry forward on every call, and an
open stream would then keep a session alive for as long as a tab stayed open, so
the inactivity timeout could never fire. The stream authenticates with
require_auth_no_slide instead.
"""

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
    """The error envelope api.js reads: a top-level "error" string."""
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


def _parse_id(raw: str) -> int | None:
    """An id from the URL, or None if it cannot possibly match a row."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


async def _json_body(request: Request) -> dict | None:
    """The request's JSON object, or None if the body is not one."""
    try:
        body = await request.json()
    except ValueError:
        return None

    return body if isinstance(body, dict) else None


@notification_bp.get("/api/notifications")
def list_notifications(request: Request, username: str = Depends(require_auth)):
    """One page of the user's notifications, newest first, with their total unread count.

    Query: `limit` (default 20, max 50), `before` (an id - only older ones), `unread=true`.
    Keyset-paged: pass the previous response's `next_cursor` as `before` for the next page.
    """
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
    """Create a notification. Body: {type, title, content?, link?, username?}.

    Defaults to the caller. Naming a different `username` needs an admin - see
    NotificationService.create for why.
    """
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


# Registered before the "/{notification_id}" route below, so "read-all" is never read as an id.
@notification_bp.post("/api/notifications/read-all")
def mark_all_notifications_read(username: str = Depends(require_auth)):
    """Mark every one of the user's notifications read."""
    try:
        return {"ok": True, "data": notification_service.mark_all_read(username)}
    except Exception:
        logger.exception("Failed to mark all notifications read")
        return _error("Failed to update notifications", 500)


@notification_bp.delete("/api/notifications")
def clear_notifications(username: str = Depends(require_auth)):
    """Delete every one of the user's notifications, read and unread. Irreversible.

    Only ever the caller's own: the user comes from the session, never from the request.
    """
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
    """Mark one notification read. Body: {"status": "read"}.

    Idempotent. Responds with the notification and the user's new unread count, so
    the badge can be corrected without another request.
    """
    parsed_id = _parse_id(notification_id)

    if parsed_id is None:
        return _error("Notification not found", 404)

    body = await _json_body(request)

    # Only unread -> read exists. Accepting a status field keeps the door open for
    # more without changing the shape; anything else is refused rather than ignored.
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
    """Server-Sent Events: one `notification` event per new notification, until disconnect.

    Starts from "now" - history comes from GET /api/notifications, and the client
    re-fetches it whenever the stream (re)opens, which is what closes any gap.
    """
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
            # Without these an intermediary may hold the stream back until it fills a
            # buffer, and the "live" feed arrives in lumps. X-Accel-Buffering is what
            # Nginx honours to turn its proxy buffering off for this one response.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
