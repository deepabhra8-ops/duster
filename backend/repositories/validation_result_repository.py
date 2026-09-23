from __future__ import annotations

from typing import Any

from core.db import get_db_session
from repositories.models import ValidationResult
from utils.logger import get_logger


logger = get_logger(__name__)


class ValidationResultRepository:
    def get(self, job_id: str) -> dict[str, Any] | None:
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
