"""SQLAlchemy-backed storage for login sessions, with sliding (rolling) expiry."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from core.db import get_db_session
from core.config import SESSION_TTL_SECONDS
from repositories.models import Session
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionRepository:
    """RDS-backed session store keyed by opaque session id, with sliding expiry."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds

    def create(self, username: str) -> str:
        """Create a new session for `username` and return its session id."""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(seconds=self._ttl_seconds)

        try:
            with get_db_session() as db_session:
                session_obj = Session(
                    session_id=session_id,
                    username=username,
                    expires_at=expires_at
                )
                db_session.add(session_obj)
                db_session.commit()
            return session_id
        except Exception:
            logger.exception("Failed to create session in RDS")
            raise

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Return the session's data if valid, sliding its expiry forward. None if missing/expired."""
        if not session_id:
            return None

        try:
            with get_db_session() as db_session:
                session_obj = db_session.query(Session).filter(
                    Session.session_id == session_id
                ).first()

                if session_obj is None:
                    return None

                if session_obj.expires_at < datetime.utcnow():
                    db_session.delete(session_obj)
                    db_session.commit()
                    return None

                # Slide expiry forward
                session_obj.expires_at = datetime.utcnow() + timedelta(seconds=self._ttl_seconds)
                db_session.commit()

                return {
                    "username": session_obj.username,
                    "expires_at": session_obj.expires_at.timestamp()
                }
        except Exception:
            logger.exception("Failed to retrieve session from RDS")
            return None

    def peek(self, session_id: str) -> str | None:
        """Return the session's username if it is still valid, WITHOUT extending it.

        get() slides the expiry forward, which is right for a request a person
        made and wrong for a connection that merely stays open: a live
        notification stream re-checking its session through get() would keep it
        alive for as long as a tab sat open, so the inactivity timeout could never
        fire. This reads only. An expired row is left for get() or logout to clear.
        """
        if not session_id:
            return None

        try:
            with get_db_session() as db_session:
                session_obj = db_session.query(Session).filter(
                    Session.session_id == session_id
                ).first()

                # expires_at is naive UTC (see create()), so compare like with like.
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                if session_obj is None or session_obj.expires_at < now:
                    return None

                return session_obj.username
        except Exception:
            # Fails closed, exactly as get() does.
            logger.exception("Failed to peek at session in RDS")
            return None

    def delete(self, session_id: str) -> None:
        """Remove a session, if it exists."""
        if not session_id:
            return
            
        try:
            with get_db_session() as db_session:
                session_obj = db_session.query(Session).filter(
                    Session.session_id == session_id
                ).first()
                
                if session_obj:
                    db_session.delete(session_obj)
                    db_session.commit()
        except Exception:
            logger.exception("Failed to delete session from RDS")


session_repository = SessionRepository(SESSION_TTL_SECONDS)
