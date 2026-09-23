"""DQ11 - a custom Spark SQL condition, optionally scoped by a filter.

Two expressions: the first says which rows the check applies to, the second
says what those rows must satisfy. A row outside the filter cannot fail.
"""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq11_custom import DQ11CustomRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


@pytest.fixture
def data(spark):
    return spark.createDataFrame(
        [("OPEN", 100), ("OPEN", -5), ("CLOSED", -20), ("CLOSED", 50)],
        ["status", "amount"],
    )


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestCondition:
    def test_rows_failing_the_condition_are_flagged(self, data, context):
        result = DQ11CustomRule().validate(
            data, "amount", parameters="|amount >= 0", context=context
        )

        # Both negative amounts fail; the filter is empty so every row applies.
        assert _failing(data, result) == 2

    def test_a_filter_limits_which_rows_are_judged(self, data, context):
        """The CLOSED row with -20 is out of scope, so only the OPEN -5 fails."""
        result = DQ11CustomRule().validate(
            data,
            "amount",
            parameters="status = 'OPEN'|amount >= 0",
            context=context,
        )

        assert _failing(data, result) == 1

    def test_a_filter_matching_nothing_fails_nothing(self, data, context):
        result = DQ11CustomRule().validate(
            data,
            "amount",
            parameters="status = 'NOPE'|amount >= 0",
            context=context,
        )

        assert _failing(data, result) == 0

    def test_a_condition_every_row_satisfies_fails_nothing(self, data, context):
        result = DQ11CustomRule().validate(
            data, "amount", parameters="|amount IS NOT NULL", context=context
        )

        assert _failing(data, result) == 0


class TestInvalidExpressions:
    def test_an_unparseable_condition_reports_not_run(self, data, context):
        """It used to pass every row, so a typo in a custom rule reported the
        data as clean rather than telling anyone the rule was broken."""
        result = DQ11CustomRule().validate(
            data, "amount", parameters="|this is not sql", context=context
        )

        assert result.was_run is False
        assert _failing(data, result) == 0

    def test_a_condition_naming_an_unknown_column_builds_but_fails_later(self, data, context):
        """expr() only parses the SQL; an unknown column is not detected until
        Spark analyses the plan, which happens after validate() returns.

        So this rule is not caught here - it surfaces when the mask is used, and
        RuleExecutor records it as a rule error, which is itself reported as NOT
        RUN. The check still never counts as passing; it just fails a layer up.
        """
        result = DQ11CustomRule().validate(
            data, "amount", parameters="|no_such_column > 0", context=context
        )

        assert result.was_run is True

        with pytest.raises(Exception):
            data.filter(~result.pass_mask).count()

    def test_an_unparseable_filter_reports_not_run(self, data, context):
        result = DQ11CustomRule().validate(
            data, "amount", parameters="not a filter(|amount >= 0", context=context
        )

        assert result.was_run is False


class TestEdgeCases:
    def test_an_empty_dataframe_is_handled(self, spark, context):
        empty = spark.createDataFrame([], "status: string, amount: int")

        result = DQ11CustomRule().validate(
            empty, "amount", parameters="|amount >= 0", context=context
        )

        assert _failing(empty, result) == 0

    def test_a_null_is_not_flagged_because_sql_comparisons_return_null(self, spark, context):
        """Worth knowing when writing a DQ11 expression: `NULL >= 0` evaluates to
        NULL, not false, and the mask `~filter | condition` is therefore NULL
        too. A filter on NULL excludes the row, so a null is neither passed nor
        failed - it simply never appears as a finding.

        That is standard SQL three-valued logic rather than a bug, but it means
        a custom rule will not catch nulls unless its expression says so
        explicitly (e.g. `amount IS NOT NULL AND amount >= 0`).
        """
        data = spark.createDataFrame([(None,), (5,)], "amount: int")

        result = DQ11CustomRule().validate(
            data, "amount", parameters="|amount >= 0", context=context
        )

        assert _failing(data, result) == 0

    def test_an_expression_that_handles_nulls_explicitly_does_flag_them(self, spark, context):
        data = spark.createDataFrame([(None,), (5,)], "amount: int")

        result = DQ11CustomRule().validate(
            data,
            "amount",
            parameters="|amount IS NOT NULL AND amount >= 0",
            context=context,
        )

        assert _failing(data, result) == 1
