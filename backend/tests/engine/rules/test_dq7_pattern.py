from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq7_pattern import DQ7PatternRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestMatching:
    def test_values_not_matching_the_pattern_fail(self, spark, context):
        data = spark.createDataFrame([("ABC",), ("AB",), ("ABCD",)], ["code"])

        result = DQ7PatternRule().validate(
            data, "code", parameters="[A-Z]{3}", context=context
        )

        assert _failing(data, result) == 2

    def test_the_match_is_anchored_at_both_ends(self, spark, context):
        data = spark.createDataFrame([("XABCX",)], ["code"])

        result = DQ7PatternRule().validate(
            data, "code", parameters="[A-Z]{3}", context=context
        )

        assert _failing(data, result) == 1

    def test_surrounding_whitespace_is_trimmed_before_matching(self, spark, context):
        data = spark.createDataFrame([("  ABC  ",)], ["code"])

        result = DQ7PatternRule().validate(
            data, "code", parameters="[A-Z]{3}", context=context
        )

        assert _failing(data, result) == 0

    def test_a_digit_pattern(self, spark, context):
        data = spark.createDataFrame([("12345",), ("1234a",)], ["zip"])

        result = DQ7PatternRule().validate(
            data, "zip", parameters=r"\d{5}", context=context
        )

        assert _failing(data, result) == 1


class TestNotConfigured:
    def test_a_blank_pattern_reports_not_run(self, spark, context):
        data = spark.createDataFrame([("anything",), ("at all",)], ["code"])

        result = DQ7PatternRule().validate(data, "code", parameters="", context=context)

        assert result.was_run is False
        assert _failing(data, result) == 0


class TestInvalidPattern:
    def test_an_unparseable_pattern_reports_not_run(self, spark, context):
        data = spark.createDataFrame([("anything",)], ["code"])

        result = DQ7PatternRule().validate(
            data, "code", parameters="[unclosed", context=context
        )

        assert result.was_run is False
        assert _failing(data, result) == 0


class TestEdgeCases:
    def test_nulls_are_exempt(self, spark, context):
        data = spark.createDataFrame([(None,)], "code: string")

        result = DQ7PatternRule().validate(
            data, "code", parameters="[A-Z]{3}", context=context
        )

        assert _failing(data, result) == 0

    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "code: string")

        result = DQ7PatternRule().validate(
            data, "code", parameters="[A-Z]{3}", context=context
        )

        assert _failing(data, result) == 0

    def test_a_numeric_column_is_matched_as_text(self, spark, context):
        data = spark.createDataFrame([(12345,), (123,)], "zip: int")

        result = DQ7PatternRule().validate(
            data, "zip", parameters=r"\d{5}", context=context
        )

        assert _failing(data, result) == 1
