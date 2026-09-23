from __future__ import annotations

import re

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, lower, trim

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ6ValueRule(BaseRule):
    rule_id = "DQ6"
    rule_name = "Value Validation"
    dimension = "Conformity"
    category = "Value Validation"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        expected = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        if not expected.strip():
            return self.create_not_run_result(
                "No expected value configured - check not run"
            )

        column = col(column_name)
        is_wildcard = "%" in expected

        if is_wildcard:
            escaped_pattern = re.escape(expected).replace(
                re.escape("%"),
                ".*",
            )
            regex = f"(?i)^{escaped_pattern}$"

            pass_mask = column.isNull() | column.cast("string").rlike(regex)
            notes = f"Value must match the pattern '{expected}'"

        else:
            trimmed = trim(column.cast("string"))

            pass_mask = (
                column.isNull()
                | (trimmed == "")
                | (lower(trimmed) == expected.strip().lower())
            )
            notes = f"Value must equal '{expected}'"

        return self.create_result(
            pass_mask=pass_mask,
            notes=notes,
        )
