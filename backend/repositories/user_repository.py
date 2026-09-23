from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.db import get_db_session
from core.config import USERS_TABLE_SCHEMA
from utils.logger import get_logger
from common.security.password_hash import hash_password


logger = get_logger(__name__)

if not re.fullmatch(r"[A-Za-z_]\w*", USERS_TABLE_SCHEMA):
    raise RuntimeError(
        f"Invalid USERS_TABLE_SCHEMA {USERS_TABLE_SCHEMA!r}: must be a plain "
        "identifier (letters, digits, underscores, not starting with a digit)."
    )

_USERS_TABLE = f"{USERS_TABLE_SCHEMA}.users"


class UserRepository:
    def __init__(self) -> None:
        pass

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                row = session.execute(
                    text(
                        "SELECT user_name AS username, password_hash, is_active, expiry_date "
                        f"FROM {_USERS_TABLE} WHERE user_name = :username"
                    ),
                    {"username": username},
                ).mappings().first()
            return dict(row) if row else None
        except Exception:
            logger.exception("Failed to look up user by username")
            raise

    def is_admin(self, username: str) -> bool:
        try:
            with get_db_session() as session:
                row = session.execute(
                    text(
                        f"SELECT is_admin FROM {_USERS_TABLE} WHERE user_name = :username"
                    ),
                    {"username": username},
                ).mappings().first()

            return bool(row and row["is_admin"])
        except Exception:
            logger.exception(
                "Failed to resolve admin flag for user '%s'; treating as non-admin",
                username,
            )
            return False

    def set_password(self, username: str, password: str) -> bool:
        return self.set_password_hash(username, hash_password(password))

    def set_password_hash(self, username: str, password_hash: str) -> bool:
        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        f"UPDATE {_USERS_TABLE} SET password_hash = :password, "
                        "modified_at = SYSUTCDATETIME() WHERE user_name = :username"
                    ),
                    {"username": username, "password": password_hash},
                )
                session.commit()
            updated = result.rowcount > 0
            if updated:
                logger.info("Updated password for user '%s'", username)
            else:
                logger.warning("Password update requested for unknown username")
            return updated
        except Exception:
            logger.exception("Failed to update password for user '%s'", username)
            raise

    def list_stored_credentials(self) -> list[tuple[str, str]]:
        try:
            with get_db_session() as session:
                rows = session.execute(
                    text(
                        "SELECT user_name AS username, password_hash "
                        f"FROM {_USERS_TABLE} WHERE password_hash IS NOT NULL"
                    )
                ).mappings().all()
            return [(row["username"], row["password_hash"]) for row in rows]
        except Exception:
            logger.exception("Failed to list stored credentials")
            raise


user_repository = UserRepository()
