from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from core.config import SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_TTL_SECONDS
from repositories.user_repository import user_repository
from services.auth_service import auth_service
from utils.logger import get_logger


logger = get_logger(__name__)


auth_bp = APIRouter()


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )


def require_auth(request: Request, response: Response) -> str:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    username = auth_service.get_current_user(session_id)

    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    _set_session_cookie(response, session_id)
    return username


def require_auth_no_slide(request: Request) -> str:
    username = auth_service.peek_current_user(request.cookies.get(SESSION_COOKIE_NAME))

    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return username


@auth_bp.post("/api/auth/login")
async def login(request: Request, response: Response):
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
        clean_username = username.strip()
        user = user_repository.get_by_username(clean_username)
        return {"ok": True, "username": clean_username, "email": user.get("email") if user else None}
    except Exception:
        logger.exception("Unexpected login route failure")
        raise


@auth_bp.post("/api/auth/logout")
async def logout(request: Request, response: Response):
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
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    username = auth_service.get_current_user(session_id)
    user = user_repository.get_by_username(username) if username else None
    return {"ok": True, "username": username, "email": user.get("email") if user else None}
