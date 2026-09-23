"""Bounded parallel execution: ordering, concurrency limits, failures, cancellation.

No Spark needed - the helper's contract is about scheduling and result handling,
and the Spark-specific part (re-applying the job group on a worker thread) is
asserted by patching the accessor rather than by booting a JVM.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from engine.core.parallel import (
    DEFAULT_MAX_TABLE_WORKERS,
    resolve_max_workers,
    run_in_parallel,
)
from utils.job_cancellation import JobCancelledError


class TestResolveMaxWorkers:
    def test_defaults_when_nothing_is_configured(self, monkeypatch):
        monkeypatch.delenv("DQ_MAX_TABLE_WORKERS", raising=False)

        assert resolve_max_workers(None) == DEFAULT_MAX_TABLE_WORKERS

    def test_job_config_wins_over_the_environment(self, monkeypatch):
        monkeypatch.setenv("DQ_MAX_TABLE_WORKERS", "8")

        assert resolve_max_workers({"max_table_workers": 2}) == 2

    def test_environment_is_used_when_config_is_silent(self, monkeypatch):
        monkeypatch.setenv("DQ_MAX_TABLE_WORKERS", "6")

        assert resolve_max_workers({}) == 6

    def test_a_nonsense_value_falls_back_rather_than_crashing(self, monkeypatch):
        monkeypatch.setenv("DQ_MAX_TABLE_WORKERS", "lots")

        assert resolve_max_workers(None) == DEFAULT_MAX_TABLE_WORKERS

    def test_never_returns_less_than_one(self, monkeypatch):
        monkeypatch.delenv("DQ_MAX_TABLE_WORKERS", raising=False)

        assert resolve_max_workers({"max_table_workers": 0}) == 1
        assert resolve_max_workers({"max_table_workers": -5}) == 1


class TestResults:
    def test_results_keep_the_input_order(self):
        """Tables finish out of order under concurrency; downstream merging of
        dimension scores must still be deterministic."""
        def slow_for_the_first(value):
            # Reverses completion order relative to submission order.
            time.sleep(0.05 if value == 0 else 0)
            return value * 10

        outcomes = run_in_parallel(list(range(4)), slow_for_the_first, max_workers=4)

        assert [o.value for o in outcomes] == [0, 10, 20, 30]
        assert [o.item for o in outcomes] == [0, 1, 2, 3]

    def test_an_empty_input_does_nothing(self):
        assert run_in_parallel([], lambda x: x, max_workers=4) == []

    def test_a_single_item_runs_without_a_pool(self):
        """The common small job must behave exactly as the sequential code did."""
        threads = set()

        def record(value):
            threads.add(threading.current_thread().name)
            return value

        outcomes = run_in_parallel(["only"], record, max_workers=4)

        assert [o.value for o in outcomes] == ["only"]
        assert threads == {threading.current_thread().name}

    def test_one_worker_runs_inline(self):
        threads = set()

        def record(value):
            threads.add(threading.current_thread().name)
            return value

        run_in_parallel([1, 2, 3], record, max_workers=1)

        assert threads == {threading.current_thread().name}


class TestConcurrencyIsBounded:
    def test_never_exceeds_the_worker_limit(self):
        """Each in-flight table holds a cached DataFrame, so the cap is what
        keeps driver and executor memory bounded."""
        active = 0
        peak = 0
        lock = threading.Lock()

        def track(value):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return value

        run_in_parallel(list(range(12)), track, max_workers=3)

        assert peak <= 3

    def test_work_actually_overlaps(self):
        """Guards against a regression to sequential execution that would still
        pass every other test here."""
        barrier = threading.Barrier(3, timeout=5)

        def wait_for_others(value):
            # Only returns if three workers reach it at once.
            barrier.wait()
            return value

        outcomes = run_in_parallel(list(range(3)), wait_for_others, max_workers=3)

        assert all(o.ok for o in outcomes)


class TestFailureIsolation:
    def test_one_failure_does_not_lose_the_other_results(self):
        def fail_on_two(value):
            if value == 2:
                raise ValueError("table 2 is broken")
            return value

        outcomes = run_in_parallel(list(range(4)), fail_on_two, max_workers=4)

        assert [o.ok for o in outcomes] == [True, True, False, True]
        assert isinstance(outcomes[2].error, ValueError)
        assert [o.value for o in outcomes if o.ok] == [0, 1, 3]

    def test_the_failing_item_is_identifiable(self):
        """So the caller can name the table in its log line."""
        outcomes = run_in_parallel(
            ["good", "bad"],
            lambda v: (_ for _ in ()).throw(RuntimeError("x")) if v == "bad" else v,
            max_workers=2,
        )

        assert outcomes[1].item == "bad"


class TestCancellation:
    def test_a_cancelled_run_reports_cancellation_per_item(self):
        cancel = threading.Event()
        cancel.set()

        outcomes = run_in_parallel([1, 2, 3], lambda v: v, max_workers=2, cancel_event=cancel)

        assert all(isinstance(o.error, JobCancelledError) for o in outcomes)

    def test_cancellation_is_also_honoured_on_the_sequential_path(self):
        cancel = threading.Event()
        cancel.set()

        outcomes = run_in_parallel([1, 2, 3], lambda v: v, max_workers=1, cancel_event=cancel)

        assert all(isinstance(o.error, JobCancelledError) for o in outcomes)

    def test_the_job_group_is_reapplied_on_worker_threads(self):
        """The trap this guards: a Spark job group is thread-local, and job_runner
        cancels a run with cancelJobGroup(job_id). Work submitted from a pool
        thread without the group would ignore that cancellation entirely - the
        user would see nothing happen while the run kept going.
        """
        with patch("engine.core.parallel._current_job_group", return_value=("job-42", "desc")), \
             patch("engine.core.parallel._apply_job_group") as apply_group:
            run_in_parallel([1, 2, 3], lambda v: v, max_workers=3)

        assert apply_group.call_count == 3
        assert {call.args for call in apply_group.call_args_list} == {("job-42", "desc")}
