from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import get_db_session
from engine.profile_map.normalize_rows import normalize_rows
from repositories.models import ProfileMapEdit, ProfileMapResult
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfileMapVersionConflict(Exception):
    def __init__(self, current_version: int, current_rows: list[dict[str, Any]]) -> None:
        super().__init__(
            "This profile map was changed by someone else while you were editing."
        )
        self.current_version = current_version
        self.current_rows = current_rows


class ProfileMapRepository:
    def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                row = session.get(ProfileMapResult, job_id)

                if row is None:
                    return None

                return {
                    "job_id": row.job_id,
                    "rows": row.rows or [],
                    "version": row.version,
                    "row_count": row.row_count,
                    "updated_at": row.updated_at,
                    "updated_by": row.updated_by,
                    "failed_tables": row.failed_tables or [],
                }
        except Exception:
            logger.exception("Failed to read profile map for job '%s'", job_id)
            raise

    def get_or_backfill(self, job_id: str) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                row = (
                    session.query(ProfileMapResult)
                    .filter(ProfileMapResult.job_id == job_id)
                    .with_for_update()
                    .first()
                )

                if row is None:
                    return None

                stored_rows = row.rows or []
                normalized = normalize_rows(stored_rows)

                if normalized != stored_rows:
                    row.rows = normalized
                    row.row_count = len(normalized)
                    row.updated_at = datetime.utcnow()
                    session.commit()

                return {
                    "job_id": row.job_id,
                    "rows": normalized,
                    "version": row.version,
                    "row_count": row.row_count,
                    "updated_at": row.updated_at,
                    "updated_by": row.updated_by,
                    "failed_tables": row.failed_tables or [],
                }
        except Exception:
            logger.exception(
                "Failed to read/backfill profile map for job '%s'", job_id
            )
            raise

    def save(
        self,
        job_id: str,
        rows: list[dict[str, Any]],
        failed_tables: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                row = session.get(ProfileMapResult, job_id)

                if row is None:
                    row = ProfileMapResult(job_id=job_id)
                    session.add(row)

                row.rows = rows
                row.row_count = len(rows)
                row.version = 1
                row.failed_tables = failed_tables or []
                row.updated_at = datetime.utcnow()
                row.updated_by = None

                session.commit()

                logger.info(
                    "Stored %s profile-map rows for job '%s'", len(rows), job_id
                )
                return {"rows": rows, "version": 1, "row_count": len(rows)}
        except Exception:
            logger.exception("Failed to store profile map for job '%s'", job_id)
            raise

    def apply_edits(
        self,
        job_id: str,
        expected_version: int,
        rows: list[dict[str, Any]],
        audit_entries: list[dict[str, Any]],
        edited_by: str,
    ) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                row = (
                    session.query(ProfileMapResult)
                    .filter(ProfileMapResult.job_id == job_id)
                    .with_for_update()
                    .first()
                )

                if row is None:
                    raise KeyError(f"No profile map for job: {job_id}")

                if row.version != expected_version:
                    raise ProfileMapVersionConflict(row.version, row.rows or [])

                new_version = row.version + 1

                row.rows = rows
                row.row_count = len(rows)
                row.version = new_version
                row.updated_at = datetime.utcnow()
                row.updated_by = edited_by

                for entry in audit_entries:
                    session.add(
                        ProfileMapEdit(
                            job_id=job_id,
                            table_name=entry["table"],
                            column_name=entry["column"],
                            row_id=entry["row_id"],
                            field=entry["field"],
                            old_value=entry.get("old_value"),
                            new_value=entry.get("new_value"),
                            version_after=new_version,
                            edited_by=edited_by,
                        )
                    )

                session.commit()

                logger.info(
                    "Applied %s profile-map cell edit(s) to job '%s' (version %s)",
                    len(audit_entries),
                    job_id,
                    new_version,
                )
                return {"rows": rows, "version": new_version}
        except (KeyError, ProfileMapVersionConflict):
            raise
        except Exception:
            logger.exception("Failed to apply profile-map edits for job '%s'", job_id)
            raise

    def list_edits(self, job_id: str, limit: int = 200) -> list[dict[str, Any]]:
        try:
            with get_db_session() as session:
                rows = (
                    session.query(ProfileMapEdit)
                    .filter(ProfileMapEdit.job_id == job_id)
                    .order_by(ProfileMapEdit.edited_at.desc())
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "table": row.table_name,
                        "column": row.column_name,
                        "row_id": str(row.row_id) if row.row_id else None,
                        "field": row.field,
                        "old_value": row.old_value,
                        "new_value": row.new_value,
                        "version_after": row.version_after,
                        "edited_by": row.edited_by,
                        "edited_at": row.edited_at.isoformat() if row.edited_at else None,
                    }
                    for row in rows
                ]
        except Exception:
            logger.exception("Failed to list profile-map edits for job '%s'", job_id)
            raise


profile_map_repository = ProfileMapRepository()
