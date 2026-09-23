from __future__ import annotations

from dateutil import parser as date_parser
from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ5RangeRule(BaseRule):
    rule_id = "DQ5"
    rule_name = "Range Validation"
    dimension = "Conformity"
    category = "Range Validation"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        minimum = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        maximum = RuleParameterParser.get(
            parameters,
            position=1,
            default="",
        )

        minimum = self._safe_strip(minimum)
        maximum = self._safe_strip(maximum)

        if not minimum and not maximum:
            return self.create_not_run_result(
                "No minimum or maximum configured - check not run"
            )

        pass_mask = self.value_mask(
            data,
            column_name,
            _RangeCheck(minimum, maximum),
        )

        return self.create_result(
            pass_mask=pass_mask,
            notes=self._range_notes(
                minimum,
                maximum,
            ),
        )

    @staticmethod
    def _range_notes(
        minimum: str,
        maximum: str,
    ) -> str:
        if minimum and maximum:
            return (
                f"Value must be between {minimum} "
                f"and {maximum}"
            )

        if minimum:
            return f"Value must be at least {minimum}"

        return f"Value must be at most {maximum}"

    @staticmethod
    def _safe_strip(value) -> str:
        if DQ5RangeRule._is_null_like(value):
            return ""

        return str(value).strip()

    @staticmethod
    def _safe_float(value):
        value_string = DQ5RangeRule._safe_strip(value)

        if not value_string:
            return None

        try:
            return float(value_string)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_date_parse(value):
        value_string = DQ5RangeRule._safe_strip(value)

        if not value_string:
            return None

        try:
            return date_parser.parse(value_string)
        except Exception:
            return None

    @staticmethod
    def _is_null_like(value) -> bool:
        if value is None:
            return True

        if isinstance(value, float) and value != value:
            return True

        return str(value).strip() == ""


class _RangeCheck:
    def __init__(self, minimum: str, maximum: str) -> None:
        self.minimum = minimum
        self.maximum = maximum

    def __call__(self, value) -> bool:
        rule = DQ5RangeRule

        if rule._is_null_like(value):
            return True

        value_string = rule._safe_strip(value)

        if not value_string:
            return True

        numeric_value = rule._safe_float(value_string)

        if numeric_value is not None:
            minimum_value = rule._safe_float(self.minimum) if self.minimum else None
            maximum_value = rule._safe_float(self.maximum) if self.maximum else None

            if minimum_value is not None and numeric_value < minimum_value:
                return False

            if maximum_value is not None and numeric_value > maximum_value:
                return False

            return True

        date_value = rule._safe_date_parse(value_string)

        if date_value is not None:
            minimum_date = rule._safe_date_parse(self.minimum) if self.minimum else None
            maximum_date = rule._safe_date_parse(self.maximum) if self.maximum else None

            if minimum_date is not None and date_value < minimum_date:
                return False

            if maximum_date is not None and date_value > maximum_date:
                return False

            return True

        if self.minimum and value_string < self.minimum:
            return False

        if self.maximum and value_string > self.maximum:
            return False

        return True
