"""DQ7: flags values that don't fully match a configured regular expression."""

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
    """Validates that a column's values fully match a configured regex pattern."""

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
        """Fail values that don't fully match the configured regex; an invalid regex skips the check."""
        pattern_string = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        if not pattern_string.strip():
            # The default used to be ".*", which matches anything: an
            # unconfigured pattern scored a confident 100% and read as a passing
            # check. Same class of lie as a skipped check scoring 100%.
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

        # Native column expression instead of a per-row Python UDF: rlike runs the match
        # entirely in the JVM via Java's regex engine. Anchoring with ^(?:...)$ reproduces
        # Python's fullmatch() semantics used above.
        column = col(column_name)
        anchored_pattern = f"^(?:{pattern_string})$"
        pass_mask = column.isNull() | trim(column.cast("string")).rlike(anchored_pattern)

        # Java's regex engine (used by rlike) and Python's `re` module aren't fully
        # identical dialects - the re.compile() above only validates against Python's rules.
        # Probe the pattern against a tiny (LIMIT 1) sample here, inside this rule's own
        # try/except, so a pattern that's valid Python regex but invalid Java regex fails
        # safely right now - same as any other rule error - rather than surfacing later as
        # an unhandled exception when TableValidator batches this mask into the table's
        # shared count aggregate.
        data.select(pass_mask.alias("_dq7_probe")).limit(1).collect()

        return self.create_result(
            pass_mask=pass_mask,
            notes=f"Value must match the pattern '{pattern_string}'",
        )
