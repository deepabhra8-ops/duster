from __future__ import annotations

import re

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, trim

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ7PatternRule(BaseRule):
    rule_id = "DQ7"
    rule_name = "Pattern / Regex Validation"
    dimension = "Conformity"
    category = "Pattern Validation"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        pattern_string = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        if not pattern_string.strip():
            return self.create_not_run_result(
                "No pattern configured - check not run"
            )

        try:
            re.compile(pattern_string)
        except re.error:
            return self.create_not_run_result(
                f"Pattern '{pattern_string}' is not a valid regular "
                f"expression - check not run"
            )

        column = col(column_name)
        anchored_pattern = f"^(?:{pattern_string})$"
        pass_mask = column.isNull() | trim(column.cast("string")).rlike(anchored_pattern)

        data.select(pass_mask.alias("_dq7_probe")).limit(1).collect()

        return self.create_result(
            pass_mask=pass_mask,
            notes=f"Value must match the pattern '{pattern_string}'",
        )
