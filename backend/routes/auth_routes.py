"""HTTP endpoints for login, logout, and session status.

Also defines `require_auth`, the FastAPI dependency other routers use (via
`include_router(..., dependencies=[Depends(require_auth)])` in app.py) to
gate access behind a valid session - new protected routers just need to be
registered the same way, no per-route changes required.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from core.config import SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_TTL_SECONDS
from services.auth_service import auth_service
from utils.logger import get_logger


logger = get_logger(__name__)


auth_bp = APIRouter()


def _set_session_cookie(response: Response, session_id: str) -> None:
    """Set the session cookie with the standard security flags and a sliding max-age."""

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )


def require_auth(request: Request, response: Response) -> str:
    """Return the logged-in username, or raise 401. Slides the session and its cookie forward."""

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    username = auth_service.get_current_user(session_id)

    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    _set_session_cookie(response, session_id)
    return username


def require_auth_no_slide(request: Request) -> str:
    """Return the logged-in username, or raise 401 - without extending the session.

    For endpoints that hold a connection open (the notification stream). require_auth
    slides the session forward on every call, which is what "active user is never
    logged out" needs; a connection that merely stays open is not activity, and
    letting it slide the session would keep it alive as long as a tab was open.
    """

    username = auth_service.peek_current_user(request.cookies.get(SESSION_COOKIE_NAME))

    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return username


@auth_bp.post("/api/auth/login")
async def login(request: Request, response: Response):
    """Verify credentials and start a session."""
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        username = str(body.get("username", ""))
        password = str(body.get("password", ""))

        session_id = auth_service.login(username, password)

        if not session_id:
            logger.warning("Login attempt rejected")
            return JSONResponse(
                {"ok": False, "error": "Invalid username or password"},
                status_code=401,
            )

        _set_session_cookie(response, session_id)
        return {"ok": True, "username": username.strip()}
    except Exception:
        logger.exception("Unexpected login route failure")
        raise


@auth_bp.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """End the current session, if any. Always succeeds (idempotent)."""
    try:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        auth_service.logout(session_id)
        response.delete_cookie(SESSION_COOKIE_NAME)
        return {"ok": True}
    except Exception:
        logger.exception("Unexpected logout route failure")
        raise


@auth_bp.get("/api/auth/me", dependencies=[Depends(require_auth)])
async def me(request: Request):
    """Return the current session's username. 401 (via require_auth) if not authenticated."""
    # require_auth already validated the session and slid the cookie forward;
    # read the username directly from the session cookie.
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    username = auth_service.get_current_user(session_id)
    return {"ok": True, "username": username}
