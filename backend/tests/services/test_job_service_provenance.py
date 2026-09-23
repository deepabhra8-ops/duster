"""get_job() must return who created a job, and when.

The results pages (ValidatorJob.jsx, ProfileMapperJob.jsx) show a "Started by"
and "Created at" line under the job id. `created_by` was always written by
create_job and was already being read inside get_job for the ownership check,
but it was never placed in the returned dict - so the field arrived at the
client as undefined and the UI rendered a dash for every job.

There is no created_at column on `jobs`: started_at carries a server_default of
now() and the row is inserted at creation time, so the `started` field doubles
as the creation timestamp. That is asserted here too, so the two stay coupled.

The repository is injected; no database involved.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.job_service import JobService


JOB_ROW = {
    "job_id": "j1",
    "status": "done",
    "name": "test-abhi",
    "description": "",
    "step": "3",
    "created_by": "admin",
    "started": "2026-09-14T10:07:00",
    "log": [],
    "params": {},
}


@pytest.fixture
def service(monkeypatch):
    from services import job_service as module

    repository = MagicMock()
    repository.get.return_value = dict(JOB_ROW)

    monkeypatch.setattr(module.validation_result_repository, "get", lambda job_id: None)
    monkeypatch.setattr(module.profile_map_repository, "get", lambda job_id: None)

    svc = JobService(repository=repository)
    monkeypatch.setattr(svc, "_get_staging_outputs", lambda job_id: [])
    monkeypatch.setattr(svc, "_path_exists", lambda path: False)
    return svc


def test_get_job_returns_created_by(service):
    assert service.get_job("j1")["created_by"] == "admin"


def test_get_job_returns_creation_timestamp(service):
    """`started` is what the UI labels "Created at" - see the module docstring."""
    assert service.get_job("j1")["started"] == "2026-09-14T10:07:00"


def test_get_job_returns_created_by_to_its_owner(service):
    """The ownership check reads the same field; passing it must not drop it."""
    assert service.get_job("j1", requester="admin")["created_by"] == "admin"


def test_get_job_hides_another_users_job(service):
    """Unchanged behaviour, asserted so the added field cannot leak an owner."""
    assert service.get_job("j1", requester="someone-else") == {}
