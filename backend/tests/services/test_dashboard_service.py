from __future__ import annotations

from unittest.mock import MagicMock

from services.dashboard_service import DashboardService


def test_job_counts_splits_status_by_step():
    session = MagicMock()
    query = session.query.return_value
    query.filter.return_value = query
    query.group_by.return_value = query
    query.all.return_value = [
        ("1", "done", 4),
        ("1", "error", 1),
        ("3", "done", 2),
        ("3", "running", 1),
    ]

    result = DashboardService._job_counts(session, "alice")

    assert result["total"] == 8
    assert result["profile_mapper"] == 5
    assert result["validator"] == 3
    assert result["profiling_by_status"] == {"done": 4, "error": 1}
    assert result["validation_by_status"] == {"done": 2, "running": 1}
    assert result["active"] == 1
