"""Spark-based unit test for DQ9ForeignKeyRule.validate(): checks column values against a
reference DataFrame stored in the execution context, and gracefully skips the check when
configuration or the reference table is missing.
"""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq9_foreign_key import DQ9ForeignKeyRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def test_values_not_present_in_the_reference_table_fail(spark, context):
    data = spark.createDataFrame([("US",), ("XX",), (None,)], schema=["country_code"])
    reference = spark.createDataFrame([("US",), ("UK",)], schema=["code"])
    context.set_reference_data("Countries", reference)

    result = DQ9ForeignKeyRule().validate(
        data, "country_code", parameters="Countries|code", context=context
    )

    values_and_pass = [
        (row["country_code"], row["__pass"])
        for row in data.withColumn("__pass", result.pass_mask).collect()
    ]

    assert values_and_pass == [("US", True), ("XX", False), (None, True)]


# The three cases below all mean "this check could not be performed". Each must
# do two things: not fail every row (the reference data's absence is not the
# data's fault), and report itself as NOT RUN so the scorer excludes it. Before,
# they only did the first - which made an unperformable check score a perfect
# 1.0 and inflated the customer-visible dimension score.


def test_missing_reference_column_configuration_is_not_run(spark, context):
    data = spark.createDataFrame([("anything",)], schema=["country_code"])

    result = DQ9ForeignKeyRule().validate(
        data, "country_code", parameters="Countries", context=context
    )

    assert data.filter(~result.pass_mask).count() == 0
    assert result.was_run is False
    assert "not run" in result.notes


def test_missing_reference_table_is_not_run(spark, context):
    """The reference table was never loaded into the context - the check must not fail
    every row just because the reference data isn't available."""
    data = spark.createDataFrame([("anything",)], schema=["country_code"])

    result = DQ9ForeignKeyRule().validate(
        data, "country_code", parameters="Countries|code", context=context
    )

    assert data.filter(~result.pass_mask).count() == 0
    assert result.was_run is False
    assert "was not found" in result.notes


def test_missing_reference_column_in_the_reference_table_is_not_run(spark, context):
    data = spark.createDataFrame([("anything",)], schema=["country_code"])
    reference = spark.createDataFrame([("US",)], schema=["code"])
    context.set_reference_data("Countries", reference)

    result = DQ9ForeignKeyRule().validate(
        data, "country_code", parameters="Countries|wrong_column", context=context
    )

    assert data.filter(~result.pass_mask).count() == 0
    assert result.was_run is False
    assert "was not found in 'Countries'" in result.notes
