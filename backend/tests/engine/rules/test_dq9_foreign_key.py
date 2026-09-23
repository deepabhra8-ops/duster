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


def test_missing_reference_column_configuration_is_not_run(spark, context):
    data = spark.createDataFrame([("anything",)], schema=["country_code"])

    result = DQ9ForeignKeyRule().validate(
        data, "country_code", parameters="Countries", context=context
    )

    assert data.filter(~result.pass_mask).count() == 0
    assert result.was_run is False
    assert "not run" in result.notes


def test_missing_reference_table_is_not_run(spark, context):
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
