from __future__ import annotations

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.core.spark_session import get_spark_session
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ9ForeignKeyRule(BaseRule):
    rule_id = "DQ9"
    rule_name = "Data Integrity / Foreign Key Validation"
    dimension = "Consistency"
    category = "Data Integrity"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        reference_table = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        reference_column = RuleParameterParser.get(
            parameters,
            position=1,
            default="",
        )

        reference_data = context.get_reference_data(
            reference_table,
        )

        if not reference_column:
            return self.create_not_run_result(
                "No reference column configured - check not run"
            )

        if reference_data is None or not isinstance(
            reference_data,
            DataFrame,
        ):
            return self.create_not_run_result(
                f"Reference table '{reference_table}' was not found - check not run"
            )

        if reference_column not in reference_data.columns:
            return self.create_not_run_result(
                f"Reference column '{reference_column}' was not found in "
                f"'{reference_table}' - check not run"
            )

        reference_values = {
            str(row[0]).strip()
            for row in reference_data.select(reference_column).dropna().collect()
        }

        broadcast_values = get_spark_session().sparkContext.broadcast(
            reference_values
        )

        pass_mask = self.value_mask(
            data,
            column_name,
            _ExistsInReference(broadcast_values),
        )

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Value must exist in "
                f"'{reference_table}.{reference_column}'"
            ),
        )

    @staticmethod
    def _safe_strip(value) -> str:
        if DQ9ForeignKeyRule._is_null_like(value):
            return ""

        return str(value).strip()

    @staticmethod
    def _is_null_like(value) -> bool:
        if value is None:
            return True

        if isinstance(value, float) and value != value:
            return True

        return str(value).strip() == ""


class _ExistsInReference:
    def __init__(self, broadcast_values) -> None:
        self.broadcast_values = broadcast_values

    def __call__(self, value) -> bool:
        if DQ9ForeignKeyRule._is_null_like(value):
            return True

        return DQ9ForeignKeyRule._safe_strip(value) in self.broadcast_values.value
