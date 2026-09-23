"""Unit tests for the /api/run pre-flight rulebook check: a Step 3 (validation) run must
be rejected synchronously - before any job is created - when no rulebook/profile map
.xlsx can be resolved on disk, instead of being accepted and only failing once the job
is already shown as "running" deep inside the pipeline.
"""
from __future__ import annotations

import asyncio

import pytest

import core.storage_layout as paths
from routes.job_routes import RULEBOOK_MISSING_MESSAGE, run_pipeline
from services.job_service import job_service


@pytest.fixture(autouse=True)
def isolate_job_filesystem(tmp_path, monkeypatch):
    """Redirect every job/profile-map path the route touches into a temp directory, so
    these tests never write into (or read stale files from) the real runtime/ folder."""
    jobs_dir = tmp_path / "jobs"
    profile_map_uploads_dir = tmp_path / "uploads" / "profile_map"
    jobs_dir.mkdir(parents=True)
    profile_map_uploads_dir.mkdir(parents=True)

    monkeypatch.setattr(paths, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(paths, "PROFILE_MAP_UPLOADS_DIR", profile_map_uploads_dir)

    return profile_map_uploads_dir


class _FakeRequest:
    """Minimal stand-in for fastapi.Request - run_pipeline() only ever calls request.json()."""

    def __init__(self, body: dict):
        self._body = body

    async def json(self):
        return self._body


def _call(body: dict, username: str = "tester"):
    # Called as a plain function (bypassing FastAPI's dependency injection), so
    # `username` - normally resolved via Depends(require_auth) - is passed directly.
    return asyncio.run(run_pipeline(_FakeRequest(body), username=username))


STEP3_PARAMS = {
    "step": "3",
    "source_type": "csv",
    "tables": [{"name": "customers", "primary_key": "id"}],
}


def test_step3_without_rulebook_is_rejected_with_400(monkeypatch):
    created = []
    monkeypatch.setattr(job_service, "create_job", lambda **kw: created.append(kw))

    response = _call(STEP3_PARAMS)

    assert response.status_code == 400
    assert RULEBOOK_MISSING_MESSAGE in response.body.decode()
    assert created == []


def test_step3_with_rulebook_present_is_accepted(monkeypatch, isolate_job_filesystem):
    (isolate_job_filesystem / "Source-DQ-Profile-Map.xlsx").write_bytes(b"stub")

    created = []
    monkeypatch.setattr(job_service, "create_job", lambda **kw: created.append(kw))
    monkeypatch.setattr(job_service, "run_job", lambda job_id: None)

    result = _call(
        {
            **STEP3_PARAMS,
            "profile_map_file": "Source-DQ-Profile-Map.xlsx",
        }
    )

    assert result["status"] == "queued"
    assert len(created) == 1


def test_step1_is_unaffected_by_the_rulebook_check(monkeypatch):
    """Step 1 (profiling) generates its own profile map - it has no rulebook to check."""
    created = []
    monkeypatch.setattr(job_service, "create_job", lambda **kw: created.append(kw))
    monkeypatch.setattr(job_service, "run_job", lambda job_id: None)

    result = _call(
        {
            "step": "1",
            "source_type": "csv",
            "tables": [{"name": "customers", "primary_key": "id"}],
        }
    )

    assert result["status"] == "queued"
    assert len(created) == 1


def test_step3_missing_profile_map_path_does_not_crash(monkeypatch):
    """resolve_profile_map_path returns None when no map is named.

    Regression guard: the route used to call .is_file() on it straight away,
    which raised AttributeError instead of returning the 400 this check exists
    to produce.
    """
    from services.config_builder import config_builder

    monkeypatch.setattr(
        config_builder, "resolve_profile_map_path", lambda job_id, params: None
    )
    monkeypatch.setattr(job_service, "create_job", lambda **kw: None)

    response = _call(STEP3_PARAMS)

    assert response.status_code == 400
    assert RULEBOOK_MISSING_MESSAGE in response.body.decode()
