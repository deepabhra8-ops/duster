from __future__ import annotations

from datetime import datetime

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ2DateFormatRule(BaseRule):
    rule_id = "DQ2"
    rule_name = "Date Format Validation"
    dimension = "Conformity"
    category = "Date Format"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        date_format = RuleParameterParser.get(
            parameters,
            position=0,
            default="%Y-%m-%d",
        )

        pass_mask = self.value_mask(
            data,
            column_name,
            _MatchesDateFormat(date_format),
        )

        return self.create_result(
            pass_mask=pass_mask,
            notes=f"Value must match the date format '{date_format}'",
        )


class _MatchesDateFormat:
    def __init__(self, date_format: str) -> None:
        self.date_format = date_format

    def __call__(self, value) -> bool:
        if value is None:
            return True

        try:
            datetime.strptime(str(value).strip(), self.date_format)
            return True
        except ValueError:
            return False
