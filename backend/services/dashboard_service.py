from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from core.db import get_db_session
from repositories.models import Job, SavedConnection, ValidationResult
from utils.logger import get_logger


logger = get_logger(__name__)

TREND_DAYS = 7

RECENT_JOB_LIMIT = 10


class DashboardService:
    def build_summary(self, username: str) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                return {
                    "jobs": self._job_counts(session, username),
                    "recent_jobs": self._recent_jobs(session, username),
                    "score_trend": self._score_trend(session, username),
                    "latest_score": self._latest_score(session, username),
                    "connections": self._connection_count(session),
                }
        except Exception:
            logger.exception("Failed to build dashboard summary for '%s'", username)
            raise

    @staticmethod
    def _job_counts(session: Any, username: str) -> dict[str, Any]:
        rows = (
            session.query(Job.step, Job.status, func.count(Job.job_id))
            .filter(Job.created_by == username)
            .group_by(Job.step, Job.status)
            .all()
        )

        by_status: dict[str, int] = {}
        by_step: dict[str, int] = {}
        profiling_by_status: dict[str, int] = {}
        validation_by_status: dict[str, int] = {}
        total = 0

        for step, status, count in rows:
            count = int(count or 0)
            total += count
            status_key = status or "unknown"
            step_key = str(step or "1")

            by_status[status_key] = by_status.get(status_key, 0) + count
            by_step[step_key] = by_step.get(step_key, 0) + count

            if step_key == "3":
                validation_by_status[status_key] = (
                    validation_by_status.get(status_key, 0) + count
                )
            else:
                profiling_by_status[status_key] = (
                    profiling_by_status.get(status_key, 0) + count
                )

        return {
            "total": total,
            "by_status": by_status,
            "profile_mapper": by_step.get("1", 0),
            "validator": by_step.get("3", 0),
            "profiling_by_status": profiling_by_status,
            "validation_by_status": validation_by_status,
            "active": sum(
                by_status.get(status, 0)
                for status in ("queued", "running", "cancelling")
            ),
        }

    @staticmethod
    def _recent_jobs(session: Any, username: str) -> list[dict[str, Any]]:
        rows = (
            session.query(Job)
            .filter(Job.created_by == username)
            .order_by(Job.started_at.desc())
            .limit(RECENT_JOB_LIMIT)
            .all()
        )

        return [
            {
                "job_id": row.job_id,
                "name": row.name,
                "step": row.step,
                "status": row.status,
                "started": row.started_at.isoformat() if row.started_at else None,
                "created_by": row.created_by,
            }
            for row in rows
        ]

    @staticmethod
    def _score_trend(session: Any, username: str) -> list[dict[str, Any]]:
        since = datetime.utcnow() - timedelta(days=TREND_DAYS)

        day = func.date(ValidationResult.created_at).label("day")

        rows = (
            session.query(
                day,
                func.avg(ValidationResult.overall_score).label("score"),
                func.count(ValidationResult.job_id).label("runs"),
            )
            .join(Job, Job.job_id == ValidationResult.job_id)
            .filter(Job.created_by == username)
            .filter(ValidationResult.created_at >= since)
            .filter(ValidationResult.overall_score.isnot(None))
            .group_by(day)
            .order_by(day)
            .all()
        )

        return [
            {
                "date": str(row.day),
                "score": round(float(row.score), 4) if row.score is not None else None,
                "runs": int(row.runs or 0),
            }
            for row in rows
        ]

    @staticmethod
    def _latest_score(session: Any, username: str) -> float | None:
        row = (
            session.query(ValidationResult.overall_score)
            .join(Job, Job.job_id == ValidationResult.job_id)
            .filter(Job.created_by == username)
            .filter(ValidationResult.overall_score.isnot(None))
            .order_by(ValidationResult.created_at.desc())
            .first()
        )

        return float(row[0]) if row and row[0] is not None else None

    @staticmethod
    def _connection_count(session: Any) -> int:
        return int(session.query(func.count(SavedConnection.id)).scalar() or 0)


dashboard_service = DashboardService()
