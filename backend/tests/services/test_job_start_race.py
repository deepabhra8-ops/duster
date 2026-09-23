from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from services.job_service import JobService


DRAFT_JOB = {
    "job_id": "j1",
    "status": "draft",
    "created_by": "alice",
    "params": {"tables": [{"name": "claim"}]},
}


class _AtomicRepository(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._status = "draft"

    def transition(self, job_id, from_statuses, to_status, **fields):
        with self._lock:
            if self._status not in from_statuses:
                return False

            self._status = to_status
            return True


@pytest.fixture
def service():
    repository = _AtomicRepository()
    repository.get.return_value = dict(DRAFT_JOB)

    job_service = JobService(repository=repository)
    job_service.submit_job = MagicMock()

    return job_service


class TestSingleStart:
    def test_a_draft_starts(self, service):
        assert service.start_draft_job("j1", requester="alice") == "ok"
        service.submit_job.assert_called_once_with("j1")

    def test_a_job_that_is_no_longer_a_draft_is_refused(self, service):
        service.repository.get.return_value = {**DRAFT_JOB, "status": "running"}

        assert service.start_draft_job("j1", requester="alice") == "not_draft"
        service.submit_job.assert_not_called()

    def test_a_draft_with_no_tables_is_refused_before_any_write(self, service):
        service.repository.get.return_value = {**DRAFT_JOB, "params": {"tables": []}}

        assert service.start_draft_job("j1", requester="alice") == "no_tables"
        service.submit_job.assert_not_called()

    def test_another_users_job_is_not_found(self, service):
        assert service.start_draft_job("j1", requester="mallory") == "not_found"
        service.submit_job.assert_not_called()


class TestConcurrentStart:
    def test_two_simultaneous_starts_trigger_exactly_one_run(self, service):
        results = []
        barrier = threading.Barrier(2, timeout=5)

        def start():
            barrier.wait()
            results.append(service.start_draft_job("j1", requester="alice"))

        threads = [threading.Thread(target=start) for _ in range(2)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert sorted(results) == ["not_draft", "ok"]
        assert service.submit_job.call_count == 1

    def test_ten_simultaneous_starts_still_trigger_one(self, service):
        results = []
        barrier = threading.Barrier(10, timeout=5)

        def start():
            barrier.wait()
            results.append(service.start_draft_job("j1", requester="alice"))

        threads = [threading.Thread(target=start) for _ in range(10)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert results.count("ok") == 1
        assert service.submit_job.call_count == 1

    def test_the_loser_never_submits(self, service):
        service.repository.transition = MagicMock(return_value=False)

        assert service.start_draft_job("j1", requester="alice") == "not_draft"
        service.submit_job.assert_not_called()
