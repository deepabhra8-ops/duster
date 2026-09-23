"""SQLAlchemy-backed storage for application user accounts.

Reads from (and, via the seed script, updates passwords in) the `users` table
created by migrations/001_initial_schema.sql - this repository still does not
insert new rows itself (only migrations/the seed do), since it has columns
(user_email_id, is_admin, audit timestamps, ...) this app doesn't know how to
populate for a brand-new account. Its relevant columns are `user_name`,
`password_hash` (a tagged hash - see common/security/password_hash.py; rows
written by another system may still be plaintext and are upgraded on their
owner's next login), `is_active`, and `expiry_date`; everywhere else in the
app deals in "username", so that translation happens only here, at the query
boundary.

The table lives in the schema named by USERS_TABLE_SCHEMA
(core/config/auth_config.py, default "dbo") rather than the connection's
default search_path - override it in backend/.env if the table lives elsewhere.

The engine is created lazily on first use (not at import time) so the
backend can still start - and serve the login page, health check, etc. -
even before DATABASE_URL is configured; only an actual login attempt needs
the database to be reachable.
"""

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

# USERS_TABLE_SCHEMA comes from trusted config (env), never request input,
# but it's interpolated directly into SQL below (can't be bound as a query
# parameter) - validate it's a plain identifier so a bad config value fails
# fast and loudly instead of producing malformed SQL.
if not re.fullmatch(r"[A-Za-z_]\w*", USERS_TABLE_SCHEMA):
    raise RuntimeError(
        f"Invalid USERS_TABLE_SCHEMA {USERS_TABLE_SCHEMA!r}: must be a plain "
        "identifier (letters, digits, underscores, not starting with a digit)."
    )

_USERS_TABLE = f"{USERS_TABLE_SCHEMA}.users"


class UserRepository:
    """Looks up accounts, and resets passwords for existing rows, in the `users` table."""

    def __init__(self) -> None:
        pass

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return the account row for `username` (password_hash, is_active, expiry_date), or None."""
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
        """Return whether `username` is flagged admin in the external users table.

        Admins can edit and delete saved connections they don't own. Treated as
        False when the column is NULL or the user is missing - a lookup failure
        must never silently grant elevated rights, so this returns False rather
        than raising.
        """
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
        """Hash and store a new password for an existing user. Returns False if no such user exists.

        Takes the plaintext and hashes it here rather than accepting an
        already-hashed value, so there is no call path through this repository
        that can write a plaintext password to the column by mistake.
        """
        return self.set_password_hash(username, hash_password(password))

    def set_password_hash(self, username: str, password_hash: str) -> bool:
        """Store an already-hashed credential. Returns False if no such user exists.

        Separate from set_password for the one case that has no plaintext to
        hash: re-tagging a legacy bare digest into `sha256$<hex>`, which is a
        pure format change on a value we cannot reverse.

        Only updates - never inserts - since this table has other required
        columns this app doesn't know how to populate for a new account.
        """
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
        """Return (username, stored password_hash) for every account.

        Only for the one-off format audit in scripts/rehash_passwords.py. The
        values are credentials - callers must never log or print them.
        """
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
