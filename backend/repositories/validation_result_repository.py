"""Storage for validator job summaries (scores, per-dimension rollups, findings).

Written once by the Glue run when validation finishes, then read back by the job
detail page and the dashboard. `overall_score` is a real column, not just a key
inside the JSON, so the dashboard can trend scores without unpacking every summary.

This replaces re-parsing the generated report workbook on each request, which on
AWS never worked at all: report_path holds a bare S3 key, so the local
Path(...).exists() check always failed and the summary came back empty.
"""

from __future__ import annotations

from typing import Any

from core.db import get_db_session
from repositories.models import ValidationResult
from utils.logger import get_logger


logger = get_logger(__name__)


class ValidationResultRepository:
    """CRUD for the `validation_results` table."""

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Return a job's stored summary, or None if validation hasn't produced one."""
        try:
            with get_db_session() as session:
                row = session.get(ValidationResult, job_id)

                if row is None:
                    return None

                return {
                    "job_id": row.job_id,
                    "overall_score": (
                        float(row.overall_score)
                        if row.overall_score is not None
                        else None
                    ),
                    "summary": row.summary or {},
                    "created_at": row.created_at,
                }
        except Exception:
            logger.exception("Failed to read validation result for job '%s'", job_id)
            raise

    def save(
        self,
        job_id: str,
        summary: dict[str, Any],
        overall_score: float | None = None,
    ) -> None:
        """Insert or replace a job's validation summary."""
        try:
            with get_db_session() as session:
                row = session.get(ValidationResult, job_id)

                if row is None:
                    row = ValidationResult(job_id=job_id)
                    session.add(row)

                row.summary = summary
                row.overall_score = (
                    overall_score
                    if overall_score is not None
                    else summary.get("overall_score")
                )

                session.commit()

                logger.info("Stored validation summary for job '%s'", job_id)
        except Exception:
            logger.exception("Failed to store validation result for job '%s'", job_id)
            raise


validation_result_repository = ValidationResultRepository()
