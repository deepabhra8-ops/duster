from __future__ import annotations

import threading

import pytest

from engine.core.execution_context import ExecutionContext
from engine.profiling.profiling_engine import ProfilingEngine
from utils.job_cancellation import JobCancelledError

pytestmark = pytest.mark.spark


TABLES = {
    "claims": "claim_id,amount\n1,100\n2,200\n3,300\n",
    "billing": "account_id,balance\n10,5\n11,15\n",
    "members": "member_id,name\nm1,Alice\nm2,Bob\nm3,Carla\nm4,Dan\n",
    "providers": "provider_id,speciality\np1,cardiology\np2,oncology\n",
}


@pytest.fixture
def csv_dir(tmp_path):
    for name, body in TABLES.items():
        (tmp_path / f"{name}.csv").write_text(body, encoding="utf-8")
    return tmp_path


def _engine(csv_dir, max_workers):
    context = ExecutionContext.from_config(
        {
            "project_name": "p",
            "source": {"type": "csv", "base_path": str(csv_dir)},
            "max_table_workers": max_workers,
        },
        run_timestamp="t",
    )
    return ProfilingEngine(context=context)


def _table_configs():
    return [{"name": name, "file": f"{name}.csv"} for name in TABLES]


def _row_count(profile):
    return profile.columns[0].total_count if profile.columns else 0


def _summarise(result):
    return {
        name: (_row_count(profile), tuple(sorted(c.column_name for c in profile.columns)))
        for name, profile in result.tables.items()
    }


class TestParallelMatchesSequential:
    def test_the_same_tables_and_statistics_are_produced(self, csv_dir):
        sequential = _engine(csv_dir, 1).profile(_table_configs())
        parallel = _engine(csv_dir, 4).profile(_table_configs())

        assert _summarise(parallel) == _summarise(sequential)

    def test_every_configured_table_is_present(self, csv_dir):
        result = _engine(csv_dir, 4).profile(_table_configs())

        assert set(result.tables) == set(TABLES)

    def test_row_counts_are_not_crossed_between_tables(self, csv_dir):
        result = _engine(csv_dir, 4).profile(_table_configs())

        assert _row_count(result.tables["claims"]) == 3
        assert _row_count(result.tables["billing"]) == 2
        assert _row_count(result.tables["members"]) == 4
        assert _row_count(result.tables["providers"]) == 2


class TestProgress:
    def test_progress_is_reported_once_per_table(self, csv_dir):
        calls = []
        lock = threading.Lock()

        def on_progress(done, total):
            with lock:
                calls.append((done, total))

        _engine(csv_dir, 4).profile(_table_configs(), progress_callback=on_progress)

        assert len(calls) == len(TABLES)
        assert sorted(done for done, _ in calls) == [1, 2, 3, 4]
        assert {total for _, total in calls} == {len(TABLES)}


class TestFailureAndCancellation:
    def test_a_missing_table_is_recorded_and_the_others_are_kept(self, csv_dir):
        configs = _table_configs() + [{"name": "ghost", "file": "ghost.csv"}]

        result = _engine(csv_dir, 4).profile(configs)

        assert set(result.tables) == set(TABLES)
        assert set(result.failed_tables) == {"ghost"}
        assert result.failed_tables["ghost"]

    def test_a_run_where_every_table_fails_still_raises(self, csv_dir):
        configs = [{"name": "ghost", "file": "ghost.csv"}]

        with pytest.raises(Exception) as excinfo:
            _engine(csv_dir, 4).profile(configs)

        assert not isinstance(excinfo.value, JobCancelledError)

    def test_cancelling_stops_the_run(self, csv_dir):
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(JobCancelledError):
            _engine(csv_dir, 4).profile(_table_configs(), cancel_event=cancel)
