from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import expr, lit

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ11CustomRule(BaseRule):
    rule_id = "DQ11"
    rule_name = "Custom Row Expression"
    dimension = "Custom"
    category = "Custom"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        params = RuleParameterParser.parse(parameters)

        filter_expr = (
            params[0].strip()
            if params
            else ""
        )

        row_expr = (
            params[1].strip()
            if len(params) > 1
            else ""
        )

        try:
            applicable = expr(filter_expr) if filter_expr else lit(True)
            passes = expr(row_expr) if row_expr else lit(True)

            mask = ~applicable | passes

            return self.create_result(
                pass_mask=mask,
                notes=f"Custom condition: {row_expr[:60]}",
            )

        except Exception as exc:
            return self.create_not_run_result(
                f"Custom expression error: {exc} - check not run"
            )
