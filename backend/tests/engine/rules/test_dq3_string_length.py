"""DQ3 - min/max string length, against a real Spark DataFrame."""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq3_string_length import DQ3StringLengthRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestBounds:
    def test_values_outside_the_range_fail(self, spark, context):
        data = spark.createDataFrame([("ab",), ("abc",), ("abcde",), ("abcdef",)], ["code"])

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        # "ab" is too short and "abcdef" too long; the bounds are inclusive.
        assert _failing(data, result) == 2

    def test_length_is_measured_after_trimming(self, spark, context):
        """Otherwise padding in a fixed-width extract reads as real content."""
        data = spark.createDataFrame([("  ab  ",)], ["code"])

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        assert _failing(data, result) == 1


class TestParameterHandling:
    def test_non_numeric_bounds_fall_back_to_defaults(self, spark, context):
        """The parser coerces silently, so this documents the actual behaviour
        rather than the behaviour one might assume."""
        data = spark.createDataFrame([("abc",)], ["code"])

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="not|numbers", context=context
        )

        # Defaults are 0..255, which "abc" satisfies.
        assert _failing(data, result) == 0


class TestEdgeCases:
    def test_nulls_are_exempt(self, spark, context):
        data = spark.createDataFrame([(None,)], "code: string")

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        assert _failing(data, result) == 0

    def test_an_empty_string_is_too_short(self, spark, context):
        data = spark.createDataFrame([("",)], ["code"])

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        assert _failing(data, result) == 1

    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "code: string")

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        assert _failing(data, result) == 0

    def test_a_numeric_column_is_measured_as_its_text(self, spark, context):
        data = spark.createDataFrame([(12345,), (1,)], ["code"])

        result = DQ3StringLengthRule().validate(
            data, "code", parameters="3|5", context=context
        )

        # "12345" fits 3..5; "1" does not.
        assert _failing(data, result) == 1
