from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app as app_module
from services import notification_retention as retention_module
from services.notification_retention import NotificationRetention

FIXED_NOW = datetime(2026, 9, 21, 12, 0, 0)


@pytest.fixture
def repo():
    repo = MagicMock()
    repo.purge_read_before.return_value = 0
    return repo


def make(repo, days=7):
    return NotificationRetention(repository=repo, retention_days=days, clock=lambda: FIXED_NOW)


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestSweep:
    def test_the_cutoff_is_seven_days_before_now(self, repo):
        make(repo, days=7).sweep()

        repo.purge_read_before.assert_called_once_with(FIXED_NOW - timedelta(days=7))

    def test_the_window_is_configurable(self, repo):
        make(repo, days=3).sweep()

        repo.purge_read_before.assert_called_once_with(FIXED_NOW - timedelta(days=3))

    def test_reports_how_many_the_repository_deleted(self, repo):
        repo.purge_read_before.return_value = 12

        assert make(repo).sweep() == 12

    def test_a_repository_failure_reaches_the_caller_so_the_loop_can_log_it(self, repo):
        repo.purge_read_before.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            make(repo).sweep()


class TestADisabledWindowNeverDeletesAnything:
    @pytest.mark.parametrize("days", [0, -1, -30])
    def test_sweep_does_nothing(self, repo, days):
        assert make(repo, days=days).sweep() == 0
        repo.purge_read_before.assert_not_called()

    @pytest.mark.parametrize("days", [0, -1])
    def test_start_starts_nothing(self, repo, days):
        retention = make(repo, days=days)

        retention.start()

        assert retention._thread is None
        assert retention.enabled is False

    def test_a_positive_window_is_enabled(self, repo):
        assert make(repo, days=7).enabled is True


class TestLifecycle:
    def test_start_is_idempotent(self, repo):
        retention = make(repo)

        with patch.object(retention, "_loop"):
            retention.start()
            first = retention._thread
            retention.start()

            assert retention._thread is first

        retention.stop()

    def test_stop_clears_the_thread(self, repo):
        retention = make(repo)

        with patch.object(retention, "_loop"):
            retention.start()
            retention.stop()

        assert retention._thread is None

    def test_stop_before_start_is_harmless(self, repo):
        make(repo).stop()


class TestLoop:
    @pytest.fixture(autouse=True)
    def fast(self, monkeypatch):
        monkeypatch.setattr(retention_module, "INITIAL_DELAY_SECONDS", 0)
        monkeypatch.setattr(retention_module, "SWEEP_INTERVAL_SECONDS", 0.01)

    def test_it_sweeps_repeatedly_until_stopped(self, repo):
        retention = make(repo)

        retention.start()
        assert wait_until(lambda: repo.purge_read_before.call_count >= 3)
        retention.stop()

        settled = repo.purge_read_before.call_count
        time.sleep(0.1)
        assert repo.purge_read_before.call_count == settled, "it kept sweeping after stop()"

    def test_a_failed_sweep_does_not_end_the_loop(self, repo):
        calls = {"n": 0}

        def flaky(_cutoff):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return 0

        repo.purge_read_before.side_effect = flaky
        retention = make(repo)

        retention.start()
        recovered = wait_until(lambda: calls["n"] >= 3)
        retention.stop()

        assert recovered, "the loop died after the first failure"


class TestWiredIntoTheApp:
    @pytest.fixture(autouse=True)
    def quiet_job_reset(self):
        with patch.object(app_module, "_reset_interrupted_jobs", MagicMock()):
            yield

    def test_the_app_starts_the_sweep_when_it_serves_and_stops_it_at_shutdown(self):
        sweep = MagicMock()

        with patch.object(app_module, "notification_retention", sweep), patch.object(
            app_module, "RUN_NOTIFICATION_PURGE", True
        ):
            with TestClient(app_module.create_app()):
                sweep.start.assert_called_once()
                sweep.stop.assert_not_called()

            sweep.stop.assert_called_once()

    def test_it_can_be_switched_off(self):
        sweep = MagicMock()

        with patch.object(app_module, "notification_retention", sweep), patch.object(
            app_module, "RUN_NOTIFICATION_PURGE", False
        ):
            with TestClient(app_module.create_app()):
                pass

        sweep.start.assert_not_called()

    def test_a_sweep_that_cannot_start_does_not_stop_the_app_serving(self):
        sweep = MagicMock()
        sweep.start.side_effect = RuntimeError("boom")

        with patch.object(app_module, "notification_retention", sweep), patch.object(
            app_module, "RUN_NOTIFICATION_PURGE", True
        ):
            with TestClient(app_module.create_app()) as client:
                assert client.get("/api/health").status_code == 200

    def test_a_sweep_that_cannot_stop_does_not_break_shutdown(self):
        sweep = MagicMock()
        sweep.stop.side_effect = RuntimeError("boom")

        with patch.object(app_module, "notification_retention", sweep), patch.object(
            app_module, "RUN_NOTIFICATION_PURGE", True
        ):
            with TestClient(app_module.create_app()):
                pass

    def test_the_real_sweeper_really_runs_while_the_app_serves(self, monkeypatch, repo):
        monkeypatch.setattr(retention_module, "INITIAL_DELAY_SECONDS", 0)
        monkeypatch.setattr(retention_module, "SWEEP_INTERVAL_SECONDS", 0.01)
        retention = make(repo)

        with patch.object(app_module, "notification_retention", retention), patch.object(
            app_module, "RUN_NOTIFICATION_PURGE", True
        ):
            with TestClient(app_module.create_app()):
                assert wait_until(lambda: repo.purge_read_before.called), "it never swept while serving"

        assert retention._thread is None, "the sweep thread outlived the app"
