from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq6_value import DQ6ValueRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestExactMatch:
    def test_only_the_expected_value_passes(self, spark, context):
        data = spark.createDataFrame([("OPEN",), ("CLOSED",), ("OPEN",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 1

    def test_the_comparison_ignores_case(self, spark, context):
        data = spark.createDataFrame([("open",), ("OPEN",), ("OpEn",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 0

    def test_surrounding_whitespace_is_ignored(self, spark, context):
        data = spark.createDataFrame([("  OPEN  ",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 0


class TestWildcard:
    def test_a_percent_suffix_matches_a_prefix(self, spark, context):
        data = spark.createDataFrame([("ACTIVE",), ("ACT",), ("INACTIVE",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="ACT%", context=context)

        assert _failing(data, result) == 1

    def test_a_surrounding_percent_matches_anywhere(self, spark, context):
        data = spark.createDataFrame([("PRE_X_POST",), ("nope",)], ["code"])

        result = DQ6ValueRule().validate(data, "code", parameters="%X%", context=context)

        assert _failing(data, result) == 1

    def test_wildcard_matching_ignores_case(self, spark, context):
        data = spark.createDataFrame([("active",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="ACT%", context=context)

        assert _failing(data, result) == 0

    def test_regex_metacharacters_are_literal(self, spark, context):
        data = spark.createDataFrame([("A.B",), ("AXB",)], ["code"])

        result = DQ6ValueRule().validate(data, "code", parameters="A.B%", context=context)

        assert _failing(data, result) == 1


class TestNotConfigured:
    def test_a_blank_expected_value_reports_not_run(self, spark, context):
        data = spark.createDataFrame([("OPEN",), ("CLOSED",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="", context=context)

        assert result.was_run is False
        assert _failing(data, result) == 0

    def test_a_whitespace_only_expected_value_reports_not_run(self, spark, context):
        data = spark.createDataFrame([("OPEN",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="   ", context=context)

        assert result.was_run is False


class TestEdgeCases:
    def test_nulls_are_exempt(self, spark, context):
        data = spark.createDataFrame([(None,)], "status: string")

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 0

    def test_blanks_are_exempt_on_the_exact_match_path(self, spark, context):
        data = spark.createDataFrame([("",), ("   ",)], ["status"])

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 0

    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "status: string")

        result = DQ6ValueRule().validate(data, "status", parameters="OPEN", context=context)

        assert _failing(data, result) == 0

    def test_a_numeric_column_is_compared_as_text(self, spark, context):
        data = spark.createDataFrame([(1,), (2,)], "code: int")

        result = DQ6ValueRule().validate(data, "code", parameters="1", context=context)

        assert _failing(data, result) == 1
