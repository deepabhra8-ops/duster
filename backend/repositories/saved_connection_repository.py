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
    def list_all(self) -> list[dict[str, Any]]:
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
        try:
            with get_db_session() as session:
                row = session.get(SavedConnection, connection_id)
                return self._to_summary(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read saved connection '%s'", connection_id)
            raise

    def get_decrypted(self, connection_id: str) -> dict[str, Any] | None:
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
        return {
            "id": row.id,
            "name": row.name,
            "db_type": row.db_type,
            "description": row.description,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }


saved_connection_repository = SavedConnectionRepository()
