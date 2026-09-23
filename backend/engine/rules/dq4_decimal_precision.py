"""DQ4: flags numeric values with more decimal places than configured."""

from __future__ import annotations

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ4DecimalPrecisionRule(BaseRule):
    """Validates that a numeric column doesn't exceed a configured decimal precision."""

    rule_id = "DQ4"
    rule_name = "Decimal Precision"
    dimension = "Conformity"
    category = "Decimal Precision"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Fail values with more decimal places than the configured precision (default 2)."""
        precision = RuleParameterParser.get_int(
            parameters,
            position=0,
            default=2,
        )

        pass_mask = self.value_mask(
            data,
            column_name,
            _WithinPrecision(precision),
        )

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Value must have at most {precision} "
                f"decimal place(s)"
            ),
        )

    @staticmethod
    def _is_null_like(value) -> bool:
        """Return whether a value should be treated as null (None, NaN, or blank)."""
        if value is None:
            return True

        if isinstance(value, float) and value != value:
            return True

        return str(value).strip() == ""


class _WithinPrecision:
    """Per-row decimal-precision check for DQ4.

    Built as a module-level callable rather than a closure so Spark can pickle
    it: the deployed engine is Cythonised, and a nested `def` there is not a
    types.FunctionType, so cloudpickle falls back to pickling by qualified name
    and fails with "Can't pickle local object". See _RangeCheck in
    engine/rules/dq5_range.py for the full explanation.
    """

    def __init__(self, precision: int) -> None:
        self.precision = precision

    def __call__(self, value) -> bool:
        if DQ4DecimalPrecisionRule._is_null_like(value):
            return True

        value_string = str(value).strip()

        try:
            float(value_string)

            if "e" in value_string.lower():
                return True

            if "." not in value_string:
                return True

            decimal_part = value_string.lstrip("+-").split(".")[-1]

            return len(decimal_part) <= self.precision

        except (ValueError, TypeError):
            return False
