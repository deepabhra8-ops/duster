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
    assert service.get_job("j1")["started"] == "2026-09-14T10:07:00"


def test_get_job_returns_created_by_to_its_owner(service):
    assert service.get_job("j1", requester="admin")["created_by"] == "admin"


def test_get_job_hides_another_users_job(service):
    assert service.get_job("j1", requester="someone-else") == {}
