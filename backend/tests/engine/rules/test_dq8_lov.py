from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq8_lov import DQ8LOVRule


pytestmark = pytest.mark.spark


@pytest.fixture
def lov_file(tmp_path):
    path = tmp_path / "statuses.csv"
    path.write_text("status\nOPEN\nCLOSED\nPENDING\n", encoding="utf-8")
    return path


@pytest.fixture
def data(spark):
    return spark.createDataFrame(
        [("OPEN",), ("CLOSED",), ("BOGUS",), (None,), ("  PENDING  ",)],
        ["status"],
    )


def _context(lov_tables: dict) -> ExecutionContext:
    return ExecutionContext.from_config(
        {
            "project_name": "test",
            "source": {"type": "csv"},
            "lov_tables": lov_tables,
        },
        run_timestamp="2026-01-01T00:00:00",
    )


def _invalid_count(data, mask) -> int:
    return data.filter(~mask).count()


class TestLovIsFound:
    def test_the_check_actually_runs(self, data, lov_file):
        context = _context({"statuses": str(lov_file)})

        result = DQ8LOVRule().validate(
            data=data, column_name="status", parameters="statuses", context=context
        )

        assert result.was_run is True
        assert "not found" not in result.notes

    def test_values_outside_the_list_fail(self, data, lov_file):
        context = _context({"statuses": str(lov_file)})

        result = DQ8LOVRule().validate(
            data=data, column_name="status", parameters="statuses", context=context
        )

        assert _invalid_count(data, result.pass_mask) == 1

    def test_nulls_are_exempt(self, spark, lov_file):
        context = _context({"statuses": str(lov_file)})
        nulls_only = spark.createDataFrame([(None,), (None,)], "status: string")

        result = DQ8LOVRule().validate(
            data=nulls_only, column_name="status", parameters="statuses", context=context
        )

        assert _invalid_count(nulls_only, result.pass_mask) == 0

    def test_the_file_is_read_once_and_cached_on_the_context(self, data, lov_file):
        context = _context({"statuses": str(lov_file)})

        DQ8LOVRule().validate(
            data=data, column_name="status", parameters="statuses", context=context
        )

        assert "statuses" in context.reference_data


class TestLovIsMissing:
    def test_an_unknown_list_reports_not_run_rather_than_passing(self, data):
        context = _context({})

        result = DQ8LOVRule().validate(
            data=data, column_name="status", parameters="nope", context=context
        )

        assert result.was_run is False
        assert result.status == "not_run"

    def test_an_unreadable_file_reports_not_run_rather_than_passing(self, data, tmp_path):
        context = _context({"statuses": str(tmp_path / "does_not_exist.csv")})

        result = DQ8LOVRule().validate(
            data=data, column_name="status", parameters="statuses", context=context
        )

        assert result.was_run is False
