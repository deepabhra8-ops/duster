from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, udf
from pyspark.sql.types import BooleanType

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ10UniquenessRule(BaseRule):
    rule_id = "DQ10"
    rule_name = "Uniqueness / Duplicate Check"
    dimension = "Uniqueness"
    category = "Uniqueness"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        columns = self._get_columns(
            data=data,
            column_name=column_name,
            parameters=parameters,
        )

        if not columns:
            return self.create_not_run_result(
                "No column(s) configured for the uniqueness check - check not run"
            )

        duplicate_keys = {
            tuple(row[column] for column in columns)
            for row in (
                data.groupBy(*columns)
                .count()
                .filter(col("count") > 1)
                .select(*columns)
                .collect()
            )
        }

        check = udf(_IsNotDuplicate(duplicate_keys), BooleanType())
        pass_mask = check(*[col(column) for column in columns])

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Combination of {', '.join(columns)} "
                f"must be unique across all rows"
            ),
        )

    @staticmethod
    def _get_columns(
        data: DataFrame,
        column_name: str,
        parameters: str,
    ) -> list[str]:
        params = RuleParameterParser.parse(parameters)

        columns_raw = (
            params[1]
            if len(params) > 1
            else params[0]
            if params
            else column_name
        )

        configured_columns = [
            column.strip()
            for column in columns_raw.split(",")
            if column.strip()
        ]

        return [
            column
            for column in configured_columns
            if column in data.columns
        ]


class _IsNotDuplicate:
    def __init__(self, duplicate_keys: set) -> None:
        self.duplicate_keys = duplicate_keys

    def __call__(self, *values) -> bool:
        if any(value is None for value in values):
            return True

        return values not in self.duplicate_keys
