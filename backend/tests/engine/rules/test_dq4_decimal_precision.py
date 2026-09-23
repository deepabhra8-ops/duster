from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq4_decimal_precision import DQ4DecimalPrecisionRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestPrecision:
    def test_values_with_too_many_decimals_fail(self, spark, context):
        data = spark.createDataFrame([("1.5",), ("1.55",), ("1.555",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 1

    def test_the_default_precision_is_two(self, spark, context):
        data = spark.createDataFrame([("1.55",), ("1.5555",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="", context=context
        )

        assert _failing(data, result) == 1

    def test_whole_numbers_always_pass(self, spark, context):
        data = spark.createDataFrame([("100",), ("0",), ("-42",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="0", context=context
        )

        assert _failing(data, result) == 0

    def test_a_sign_does_not_count_toward_the_decimals(self, spark, context):
        data = spark.createDataFrame([("-1.55",), ("+1.55",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 0


class TestNonNumeric:
    def test_text_fails(self, spark, context):
        data = spark.createDataFrame([("abc",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 1

    def test_scientific_notation_is_exempt(self, spark, context):
        data = spark.createDataFrame([("1.23456e10",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 0


class TestEdgeCases:
    def test_nulls_are_exempt(self, spark, context):
        data = spark.createDataFrame([(None,), (None,)], "amount: string")

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 0

    def test_blanks_are_exempt(self, spark, context):
        data = spark.createDataFrame([("",), ("   ",)], ["amount"])

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 0

    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "amount: string")

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 0

    def test_a_real_double_column_is_handled(self, spark, context):
        data = spark.createDataFrame([(1.5,), (1.555,)], "amount: double")

        result = DQ4DecimalPrecisionRule().validate(
            data, "amount", parameters="2", context=context
        )

        assert _failing(data, result) == 1
