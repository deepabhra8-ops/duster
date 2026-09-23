"""Storage for saved database connections (name + encrypted connection details).

Connection details are encrypted at rest (common/security/crypto.py) because they hold real
credentials for external databases. Only non-secret fields are ever returned by
the list/summary methods; decryption is a separate, explicit call.

Schema is owned by backend/migrations/002_ui_v2_schema.sql - this module never
issues DDL.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import func

from core.db import get_db_session
from repositories.models import SavedConnection
from common.security.crypto import decrypt_json, encrypt_json
from utils.logger import get_logger


logger = get_logger(__name__)


class SavedConnectionRepository:
    """CRUD for the `saved_connections` table."""

    def list_all(self) -> list[dict[str, Any]]:
        """Return every saved connection's non-secret fields, newest first.

        Connections are shared: any authenticated user may see and use them.
        Editing and deleting are owner-only, enforced in the service layer using
        the `created_by` returned here.
        """
        try:
            with get_db_session() as session:
                rows = (
                    session.query(SavedConnection)
                    .order_by(SavedConnection.created_at.desc())
                    .all()
                )
                return [self._to_summary(row) for row in rows]
        except Exception:
            logger.exception("Failed to list saved connections")
            raise

    def list_page(
        self,
        search: str = "",
        db_type: str = "",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of connections plus the total matching count.

        Filtering and pagination happen in SQL, mirroring JobRepository.list_page -
        used by the Connections manager page; list_all() above stays untouched for
        the job wizard's connection picker, which needs every connection to
        search/select from rather than one page of them.
        """
        try:
            with get_db_session() as session:
                query = session.query(SavedConnection)

                if search:
                    pattern = f"%{search.strip().lower()}%"
                    query = query.filter(func.lower(SavedConnection.name).like(pattern))

                if db_type:
                    query = query.filter(SavedConnection.db_type == db_type)

                total = query.count()

                query = query.order_by(
                    SavedConnection.created_at.asc()
                    if sort_order == "asc"
                    else SavedConnection.created_at.desc()
                )

                offset = max(page - 1, 0) * page_size
                rows = query.limit(page_size).offset(offset).all()

                return [self._to_summary(row) for row in rows], total
        except Exception:
            logger.exception("Failed to list saved connections (paginated)")
            raise

    def get(self, connection_id: str) -> dict[str, Any] | None:
        """Return one connection's non-secret fields (including `created_by` for
        ownership checks), or None if it doesn't exist."""
        try:
            with get_db_session() as session:
                row = session.get(SavedConnection, connection_id)
                return self._to_summary(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read saved connection '%s'", connection_id)
            raise

    def get_decrypted(self, connection_id: str) -> dict[str, Any] | None:
        """Return one connection with its details decrypted, or None if absent.

        Used server-side when resolving a job's `connection_id` at run time, and
        by the owner-only reveal route that pre-fills the edit form.
        """
        try:
            with get_db_session() as session:
                row = session.get(SavedConnection, connection_id)

                if row is None:
                    return None

                return {
                    "id": row.id,
                    "name": row.name,
                    "db_type": row.db_type,
                    "created_by": row.created_by,
                    "connection_details": decrypt_json(row.connection_details_encrypted),
                }
        except Exception:
            logger.exception("Failed to decrypt saved connection '%s'", connection_id)
            raise

    def create(
        self,
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
        created_by: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Encrypt and store a new connection; return its non-secret fields."""
        connection_id = secrets.token_urlsafe(12)

        try:
            with get_db_session() as session:
                row = SavedConnection(
                    id=connection_id,
                    name=name,
                    db_type=db_type,
                    description=description or None,
                    connection_details_encrypted=encrypt_json(connection_details),
                    created_by=created_by,
                )
                session.add(row)
                session.commit()

                logger.info("Created saved connection '%s' (%s)", connection_id, db_type)
                return self._to_summary(row)
        except Exception:
            logger.exception("Failed to create saved connection")
            raise

    def update(
        self,
        connection_id: str,
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
        description: str | None = None,
    ) -> dict[str, Any] | None:
        """Re-encrypt and overwrite an existing connection; return its updated
        non-secret fields, or None if it doesn't exist.

        Deliberately never touches `created_by` - ownership doesn't transfer on edit.
        """
        try:
            with get_db_session() as session:
                row = session.get(SavedConnection, connection_id)

                if row is None:
                    return None

                row.name = name
                row.db_type = db_type
                row.description = description or None
                row.connection_details_encrypted = encrypt_json(connection_details)
                row.updated_at = datetime.utcnow()

                session.commit()

                logger.info("Updated saved connection '%s'", connection_id)
                return self._to_summary(row)
        except Exception:
            logger.exception("Failed to update saved connection '%s'", connection_id)
            raise

    def delete(self, connection_id: str) -> bool:
        """Delete a connection and return whether it existed.

        Jobs referencing it keep their history - the FK is ON DELETE SET NULL.
        """
        try:
            with get_db_session() as session:
                row = session.get(SavedConnection, connection_id)

                if row is None:
                    return False

                session.delete(row)
                session.commit()

                logger.info("Deleted saved connection '%s'", connection_id)
                return True
        except Exception:
            logger.exception("Failed to delete saved connection '%s'", connection_id)
            raise

    @staticmethod
    def _to_summary(row: SavedConnection) -> dict[str, Any]:
        """Map a row to its non-secret representation. Never includes credentials."""
        return {
            "id": row.id,
            "name": row.name,
            "db_type": row.db_type,
            "description": row.description,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }


saved_connection_repository = SavedConnectionRepository()
