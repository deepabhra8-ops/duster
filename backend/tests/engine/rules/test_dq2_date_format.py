from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq2_date_format import DQ2DateFormatRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestDefaultFormat:
    def test_iso_dates_pass_and_others_fail(self, spark, context):
        data = spark.createDataFrame(
            [("2023-01-01",), ("2023-12-31",), ("31/12/2023",), ("nonsense",)],
            ["d"],
        )

        result = DQ2DateFormatRule().validate(data, "d", parameters="", context=context)

        assert _failing(data, result) == 2


class TestConfiguredFormat:
    def test_a_configured_pattern_is_honoured(self, spark, context):
        data = spark.createDataFrame([("31/12/2023",), ("2023-12-31",)], ["d"])

        result = DQ2DateFormatRule().validate(
            data, "d", parameters="%d/%m/%Y", context=context
        )

        assert _failing(data, result) == 1

    def test_a_real_date_that_does_not_exist_fails(self, spark, context):
        data = spark.createDataFrame([("2023-02-30",)], ["d"])

        result = DQ2DateFormatRule().validate(data, "d", parameters="", context=context)

        assert _failing(data, result) == 1


class TestEdgeCases:
    def test_nulls_are_exempt(self, spark, context):
        data = spark.createDataFrame([(None,), (None,)], "d: string")

        result = DQ2DateFormatRule().validate(data, "d", parameters="", context=context)

        assert _failing(data, result) == 0

    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "d: string")

        result = DQ2DateFormatRule().validate(data, "d", parameters="", context=context)

        assert _failing(data, result) == 0

    def test_a_numeric_column_does_not_crash_the_rule(self, spark, context):
        data = spark.createDataFrame([(20230101,), (1,)], ["d"])

        result = DQ2DateFormatRule().validate(data, "d", parameters="", context=context)

        assert _failing(data, result) == 2
