"""Aggregate statistics for the Home dashboard.

Everything here is scoped to the requesting user, matching how jobs are scoped
everywhere else - one user's dashboard must not count another's runs.

Queries aggregate in SQL rather than loading rows and counting in Python, because
this endpoint is hit on every dashboard load.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from core.db import get_db_session
from repositories.models import Job, SavedConnection, ValidationResult
from utils.logger import get_logger


logger = get_logger(__name__)

# How far back the score trend looks. A week rather than a month: at 30 days the
# chart plotted whichever handful of days happened to have runs, spread across a
# month, so neighbouring points could be weeks apart and the line implied a
# gradient that nothing measured. Seven days is a window a reader can hold in
# mind, and the points in it are genuinely adjacent.
TREND_DAYS = 7

# How many recent jobs the activity list shows. Sized to fill the dashboard
# panel without running far past it. The panel shares its column with the Jobs
# by Type chart now rather than spanning the row's full height, so it holds
# roughly half what it used to - 20 rows left most of the list behind a scroll
# nobody would reach. 10 covers a 2560x1440 screen with a row to spare, and
# smaller screens simply scroll sooner.
RECENT_JOB_LIMIT = 10


class DashboardService:
    """Builds the dashboard summary in a handful of aggregate queries."""

    def build_summary(self, username: str) -> dict[str, Any]:
        """Return counts, recent activity, and the DQ score trend for one user."""
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
        """Counts by status and by step, from one grouped query."""
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
                # Step 1 is Profile Mapper; any other non-validator step rolls up here.
                profiling_by_status[status_key] = (
                    profiling_by_status.get(status_key, 0) + count
                )

        return {
            "total": total,
            "by_status": by_status,
            # Named rather than left as raw step numbers, since that is what the
            # dashboard actually labels them.
            "profile_mapper": by_step.get("1", 0),
            "validator": by_step.get("3", 0),
            # Per-type status breakdowns for the Jobs-by-Type donuts on Home.jsx.
            "profiling_by_status": profiling_by_status,
            "validation_by_status": validation_by_status,
            "active": sum(
                by_status.get(status, 0)
                for status in ("queued", "running", "cancelling")
            ),
        }

    @staticmethod
    def _recent_jobs(session: Any, username: str) -> list[dict[str, Any]]:
        """The most recent jobs, for the activity list."""
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
        """Average overall DQ score per day over the trend window.

        Reads validation_results.overall_score as a column - the reason it is stored
        as one rather than only inside the summary JSON.
        """
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
        """The most recent validation's overall score, for the headline tile."""
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
        """Saved connections are shared, so this is deliberately not user-scoped."""
        return int(session.query(func.count(SavedConnection.id)).scalar() or 0)


dashboard_service = DashboardService()
