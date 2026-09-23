"""Spark-based unit test for DQ5RangeRule.validate() against a real small DataFrame,
covering the numeric-range branch and the "no bounds configured" branch.
"""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq5_range import DQ5RangeRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def test_numeric_values_outside_the_configured_range_fail(spark, context):
    data = spark.createDataFrame([(5,), (50,), (150,), (None,)], schema=["age"])

    result = DQ5RangeRule().validate(data, "age", parameters="10|100", context=context)

    values_and_pass = [
        (row["age"], row["__pass"])
        for row in data.withColumn("__pass", result.pass_mask).collect()
    ]

    assert values_and_pass == [(5, False), (50, True), (150, False), (None, True)]


def test_no_bounds_configured_is_not_run(spark, context):
    """A range check with neither bound set has nothing to check against.

    It used to pass every row and score 1.0, so an analyst who forgot to fill in
    the bounds saw a perfect Conformity score for a check that never ran. It now
    reports NOT RUN and is excluded from scoring; the rows still cannot fail,
    because their validity is genuinely unknown.
    """
    data = spark.createDataFrame([(5,), (999,)], schema=["age"])

    result = DQ5RangeRule().validate(data, "age", parameters="", context=context)

    assert data.filter(~result.pass_mask).count() == 0
    assert result.was_run is False
    assert "not run" in result.notes
