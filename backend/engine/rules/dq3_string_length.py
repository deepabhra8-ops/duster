"""DQ3: flags string values outside a configured min/max length range."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, length, trim

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ3StringLengthRule(BaseRule):
    """Validates that a column's string length falls within a configured range."""

    rule_id = "DQ3"
    rule_name = "String Length"
    dimension = "Conformity"
    category = "String Length"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Fail values whose length falls outside [min, max] (defaults 0-255)."""
        minimum = RuleParameterParser.get_int(
            parameters,
            position=0,
            default=0,
        )

        maximum = RuleParameterParser.get_int(
            parameters,
            position=1,
            default=255,
        )

        # Native column expression instead of a per-row Python UDF: length()/trim() run
        # entirely in the JVM, with no per-row JVM<->Python serialization.
        column = col(column_name)

        pass_mask = column.isNull() | (
            length(trim(column.cast("string"))).between(minimum, maximum)
        )

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Value length must be between "
                f"{minimum} and {maximum} characters"
            ),
        )
