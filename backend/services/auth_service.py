from __future__ import annotations

from datetime import datetime, timezone

from repositories.session_repository import session_repository
from repositories.user_repository import user_repository
from utils.logger import get_logger
from common.security.password_hash import verify_password


logger = get_logger(__name__)


class AuthService:
    def login(self, username: str, password: str) -> str | None:
        username = (username or "").strip()

        if not username or not password:
            return None

        user = user_repository.get_by_username(username)

        if not user:
            logger.warning("Login failed: unknown username")
            return None

        if not user["is_active"]:
            logger.warning("Login failed: account inactive for '%s'", username)
            return None

        expiry_date = user["expiry_date"]
        if expiry_date is not None and expiry_date < datetime.now(timezone.utc).replace(tzinfo=None):
            logger.warning("Login failed: account expired for '%s'", username)
            return None

        ok, needs_rehash = verify_password(password, user["password_hash"])

        if not ok:
            logger.warning("Login failed: incorrect password for '%s'", username)
            return None

        if needs_rehash:
            self._upgrade_stored_password(user["username"], password)

        session_id = session_repository.create(user["username"])
        logger.info("Login succeeded for '%s'", username)
        return session_id

    @staticmethod
    def _upgrade_stored_password(username: str, password: str) -> None:
        try:
            user_repository.set_password(username, password)
            logger.info("Upgraded stored password format for '%s'", username)
        except Exception:
            logger.exception(
                "Could not upgrade stored password format for '%s'; login proceeds",
                username,
            )

    def logout(self, session_id: str | None) -> None:
        if session_id:
            session_repository.delete(session_id)

    def get_current_user(self, session_id: str | None) -> str | None:
        session = session_repository.get(session_id) if session_id else None
        return session["username"] if session else None

    def peek_current_user(self, session_id: str | None) -> str | None:
        return session_repository.peek(session_id) if session_id else None


auth_service = AuthService()
