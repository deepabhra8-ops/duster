"""DQ10 - composite-key uniqueness."""
from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.dq10_uniqueness import DQ10UniquenessRule

pytestmark = pytest.mark.spark


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


def _failing(data, result):
    return data.filter(~result.pass_mask).count()


class TestSingleColumn:
    def test_every_row_of_a_duplicated_key_fails(self, spark, context):
        """Both copies are flagged: which one is the 'real' record is not
        something the rule can decide."""
        data = spark.createDataFrame([("a",), ("b",), ("a",)], ["claim_id"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id", context=context
        )

        assert _failing(data, result) == 2

    def test_all_distinct_values_pass(self, spark, context):
        data = spark.createDataFrame([("a",), ("b",), ("c",)], ["claim_id"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id", context=context
        )

        assert _failing(data, result) == 0


class TestCompositeKey:
    def test_uniqueness_is_judged_across_the_whole_combination(self, spark, context):
        data = spark.createDataFrame(
            [("a", "1"), ("a", "2"), ("a", "1")],
            ["claim_id", "line_no"],
        )

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id,line_no", context=context
        )

        # ("a","1") appears twice; ("a","2") is unique.
        assert _failing(data, result) == 2

    def test_the_column_list_may_sit_in_the_second_parameter(self, spark, context):
        """The profile map's parameter cell carries the column list in position
        1 when a first positional value is present."""
        data = spark.createDataFrame([("a",), ("a",)], ["claim_id"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="ignored|claim_id", context=context
        )

        assert _failing(data, result) == 2

    def test_spacing_in_the_list_is_tolerated(self, spark, context):
        data = spark.createDataFrame([("a", "1"), ("a", "1")], ["claim_id", "line_no"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters=" claim_id , line_no ", context=context
        )

        assert _failing(data, result) == 2


class TestNulls:
    def test_a_row_with_a_null_in_the_key_is_exempt(self, spark, context):
        """A null key is a completeness problem, which DQ1 reports - treating
        two nulls as duplicates of each other would double-report it."""
        data = spark.createDataFrame([(None,), (None,)], "claim_id: string")

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id", context=context
        )

        assert _failing(data, result) == 0

    def test_a_null_in_any_part_of_a_composite_key_exempts_the_row(self, spark, context):
        data = spark.createDataFrame(
            [("a", None), ("a", None)],
            "claim_id: string, line_no: string",
        )

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id,line_no", context=context
        )

        assert _failing(data, result) == 0


class TestNoParameters:
    def test_no_parameters_uses_the_selected_rule_column(self, spark, context):
        """A single-field uniqueness rule needs no parameter: the rule's
        selected column is its key."""
        data = spark.createDataFrame([("a",), ("a",)], ["claim_id"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="", context=context
        )

        assert result.was_run is True
        assert _failing(data, result) == 2

    def test_columns_absent_from_the_data_are_ignored(self, spark, context):
        """A profile map naming a column the source no longer has must not
        crash the run."""
        data = spark.createDataFrame([("a",), ("a",)], ["claim_id"])

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id,gone_away", context=context
        )

        assert _failing(data, result) == 2


class TestEdgeCases:
    def test_an_empty_dataframe_is_handled(self, spark, context):
        data = spark.createDataFrame([], "claim_id: string")

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id", context=context
        )

        assert _failing(data, result) == 0

    def test_numeric_keys_are_handled(self, spark, context):
        data = spark.createDataFrame([(1,), (2,), (1,)], "claim_id: int")

        result = DQ10UniquenessRule().validate(
            data, "claim_id", parameters="claim_id", context=context
        )

        assert _failing(data, result) == 2
