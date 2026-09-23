"""DQ1: flags null or blank values in a column."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, trim

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_registry import register_rule


@register_rule
class DQ1CompletenessRule(BaseRule):
    """Validates that a column's values are not null or blank."""

    rule_id = "DQ1"
    rule_name = "Completeness / Null Check"
    dimension = "Completeness"
    category = "Completeness"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Fail values that are null or an empty/whitespace-only string."""
        column = col(column_name)

        pass_mask = column.isNotNull() & (trim(column.cast("string")) != "")

        return self.create_result(
            pass_mask=pass_mask,
            notes="Value must not be null or blank",
        )
