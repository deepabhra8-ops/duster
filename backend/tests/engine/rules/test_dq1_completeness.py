from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq1_completeness import DQ1CompletenessRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def test_null_and_blank_values_fail_non_blank_values_pass(spark, context):
    data = spark.createDataFrame(
        [("Alice",), (None,), ("   ",), ("",), ("Bob",)],
        schema=["name"],
    )

    result = DQ1CompletenessRule().validate(data, "name", parameters="", context=context)

    passing = data.filter(result.pass_mask).count()
    failing = data.filter(~result.pass_mask).count()

    assert passing == 2
    assert failing == 3
