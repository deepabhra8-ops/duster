"""One table failing must not throw away the tables that profiled fine.

Spark-free counterpart to test_profiling_engine_parallel.py: the source and the
profiler are fakes, so this pins the engine's bookkeeping - which tables are kept,
which are recorded as failed, and when the run as a whole still fails - without a
JVM.
"""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import TableProfileResult
from engine.profiling.profiling_engine import ProfilingEngine
from utils.job_cancellation import JobCancelledError


class _FakeData:
    def cache(self):
        return self

    def unpersist(self):
        return self


class _FakeSource:
    def __init__(self, broken: dict[str, BaseException]):
        self.broken = broken

    def read(self, table_config):
        error = self.broken.get(table_config["name"])

        if error is not None:
            raise error

        return _FakeData()


class _FakeSourceRegistry:
    def __init__(self, source):
        self.source = source

    def get(self, **_kwargs):
        return self.source


class _FakeProfiler:
    def profile(self, data, table_config):
        return TableProfileResult(table_name=table_config["name"], columns=[])


class _FakeProfilerFactory:
    def create(self, **_kwargs):
        return _FakeProfiler()


def _engine(broken: dict[str, BaseException]):
    context = ExecutionContext.from_config(
        {
            "project_name": "p",
            "source": {"type": "csv", "base_path": "unused"},
            "max_table_workers": 4,
        },
        run_timestamp="t",
    )
    return ProfilingEngine(
        context=context,
        source_registry=_FakeSourceRegistry(_FakeSource(broken)),
        profiler_factory=_FakeProfilerFactory(),
    )


def _tables(*names):
    return [{"name": name, "file": f"{name}.csv"} for name in names]


def test_the_good_tables_are_kept_and_the_bad_one_is_recorded():
    engine = _engine({"orders": FileNotFoundError("orders.csv not found\nat line 1")})

    result = engine.profile(_tables("customers", "orders", "products"))

    assert set(result.tables) == {"customers", "products"}
    # Only the first line survives - a Spark trace would swamp the UI.
    assert result.failed_tables == {"orders": "orders.csv not found"}


def test_a_clean_run_records_no_failures():
    result = _engine({}).profile(_tables("customers", "orders"))

    assert set(result.tables) == {"customers", "orders"}
    assert result.failed_tables == {}


def test_every_table_failing_fails_the_run():
    engine = _engine({
        "customers": ValueError("bad header"),
        "orders": ValueError("empty file"),
    })

    with pytest.raises(ValueError):
        engine.profile(_tables("customers", "orders"))


def test_progress_counts_failed_tables_as_finished():
    calls = []
    engine = _engine({"orders": ValueError("boom")})

    engine.profile(
        _tables("customers", "orders", "products"),
        progress_callback=lambda done, total: calls.append((done, total)),
    )

    assert sorted(done for done, _ in calls) == [1, 2, 3]
    assert {total for _, total in calls} == {3}


def test_a_cancellation_still_ends_the_whole_run():
    engine = _engine({"orders": JobCancelledError("Job cancelled by user")})

    with pytest.raises(JobCancelledError):
        engine.profile(_tables("customers", "orders"))
