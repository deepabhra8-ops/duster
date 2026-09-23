from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.job_service import JobService


def _draft(**params):
    base = {
        "step": "3",
        "source_type": "database",
        "tables": [{"schema": "public", "name": "claim", "primary_key": "claim_id"}],
        "connection_id": "c1",
        "profile_map_file": "abc_map.xlsx",
    }
    base.update(params)
    return {
        "job_id": "j1",
        "status": "draft",
        "step": "3",
        "created_by": "tester",
        "params": base,
    }


@pytest.fixture
def service():
    repository = MagicMock()
    repository.transition.return_value = True
    return JobService(repository=repository)


@pytest.fixture(autouse=True)
def resolvable_connection(monkeypatch, tmp_path):
    from services import job_service as module

    monkeypatch.setattr(
        module.config_builder,
        "resolve_connection",
        lambda params: {
            "databaseType": "postgresql",
            "connectionDetails": {"host": "db"},
        },
    )

    existing_file = tmp_path / "abc_map.xlsx"
    existing_file.write_bytes(b"")

    monkeypatch.setattr(
        module.config_builder,
        "resolve_profile_map_path",
        lambda job_id, params: existing_file,
    )


def _start(service, job):
    service.repository.get.return_value = job
    return service.start_draft_job("j1", requester="tester")


class TestARunnableDraftStarts:
    def test_a_complete_draft_is_accepted(self, service, monkeypatch):
        monkeypatch.setattr(service, "submit_job", lambda job_id: None)

        assert _start(service, _draft()) == "ok"

    def test_a_draft_sourced_from_a_profile_mapper_job_needs_no_workbook(
        self, service, monkeypatch
    ):
        monkeypatch.setattr(service, "submit_job", lambda job_id: None)

        job = _draft(profile_map_file="", profile_map_source_job_id="src-1")

        assert _start(service, job) == "ok"


class TestIncompleteDraftsAreRefused:
    def test_no_tables(self, service):
        assert _start(service, _draft(tables=[])) == "no_tables"

    def test_table_entries_that_are_not_objects(self, service):
        assert _start(service, _draft(tables=["claim"])) == "bad_tables"

    def test_a_connection_that_no_longer_resolves(self, service, monkeypatch):
        from services import job_service as module

        monkeypatch.setattr(
            module.config_builder,
            "resolve_connection",
            lambda params: {"databaseType": "", "connectionDetails": {}},
        )

        assert _start(service, _draft()) == "no_connection"

    def test_no_profile_map_at_all(self, service):
        assert _start(service, _draft(profile_map_file="")) == "no_profile_map"

    def test_a_workbook_that_is_not_actually_on_disk(self, service, monkeypatch):
        from services import job_service as module

        monkeypatch.setattr(
            module.config_builder,
            "resolve_profile_map_path",
            lambda job_id, params: Path("does/not/exist.xlsx"),
        )

        assert _start(service, _draft()) == "no_profile_map"

    def test_nothing_is_submitted_when_the_preflight_refuses(self, service):
        submitted = []
        service.submit_job = lambda job_id: submitted.append(job_id)

        _start(service, _draft(profile_map_file=""))

        assert submitted == []
        service.repository.transition.assert_not_called()


class TestStepOneIsUnaffected:
    def test_a_profile_mapper_draft_needs_no_profile_map(self, service, monkeypatch):
        monkeypatch.setattr(service, "submit_job", lambda job_id: None)

        job = _draft(step="1", profile_map_file="")
        job["step"] = "1"

        assert _start(service, job) == "ok"
