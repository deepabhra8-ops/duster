"""DQ6: flags values that don't equal (or match a %-wildcard pattern of) a configured expected value."""

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
    """Validates that a column's values equal (or wildcard-match) a configured expected value."""

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
        """Fail values that don't equal the expected value, or don't match it as a '%'-wildcard pattern."""
        expected = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        if not expected.strip():
            # With no expected value the comparison target is the empty string,
            # so every non-empty value was reported invalid - a column of 100
            # good values came back 0% with 100 findings, and the note read
            # "Value must equal ''". A rule nobody configured must say so
            # rather than manufacture findings.
            return self.create_not_run_result(
                "No expected value configured - check not run"
            )

        column = col(column_name)
        is_wildcard = "%" in expected

        if is_wildcard:
            # Native column expression instead of a per-row Python UDF: the '%'-wildcard
            # pattern is built once here (in Python, on the small config string - cheap),
            # then matched entirely in the JVM via rlike. re.escape() keeps every character
            # but '%' literal, exactly as the original per-row regex did, so behavior is
            # unchanged (unlike SQL LIKE, '_' is not treated as a single-char wildcard here).
            escaped_pattern = re.escape(expected).replace(
                re.escape("%"),
                ".*",
            )
            regex = f"(?i)^{escaped_pattern}$"

            pass_mask = column.isNull() | column.cast("string").rlike(regex)
            notes = f"Value must match the pattern '{expected}'"

        else:
            # Native equivalent of the old _is_null_like() check + case-insensitive
            # stripped-string equality. Only the extremely rare case of a float NaN stored
            # in an otherwise string-typed value column isn't reproduced natively - Spark's
            # isNull() doesn't consider NaN null - since DQ6 runs on value/category columns
            # where that never occurs in practice.
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
