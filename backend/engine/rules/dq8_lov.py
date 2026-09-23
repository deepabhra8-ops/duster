"""DQ8: flags values not present in a configured List of Values (LOV) reference list."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import coalesce, col, lit, trim
from pyspark.sql.types import StringType

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ8LOVRule(BaseRule):
    """Validates that a column's values belong to a configured LOV reference list."""

    rule_id = "DQ8"
    rule_name = "LOV / Reference Data Validation"
    dimension = "Consistency"
    category = "Reference Data Validation"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Fail values not found in the named LOV; a missing LOV skips the check."""
        lov_name = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

        # DQ8 is inferred for likely-categorical columns (see RuleInference), so a
        # rule can reach here with no LOV named at all. Saying the list '' was not
        # found described that as a lookup failure; the check was never configured.
        if not lov_name:
            return self.create_not_run_result(
                "No reference list named in the rule parameters - check not run"
            )

        lov_values = context.get_reference_data(
            lov_name,
        )

        if lov_values is None:
            return self.create_not_run_result(
                f"Reference list '{lov_name}' was not found - check not run"
            )

        valid_values = {
            str(value).strip()
            for value in lov_values
        }

        column = col(column_name)

        # The comparison happens in the COLUMN's type, not in text. A LOV comes
        # from a CSV, where every value is a string and nothing carries a type,
        # so a list written for a boolean column says "1" while Spark renders
        # that column as "true" - comparing the two as text failed every row of
        # otherwise valid data. Casting each list value to the column's own type
        # lets Spark apply its own literal rules, which is why 1/0/yes/no all
        # read as booleans, "10.5" matches a decimal(10,2) 10.50, and
        # "2024-01-01" matches a date.
        #
        # The runtime schema is used rather than the type declared in the profile
        # map: it is the type the values actually have once read, and the one the
        # cast has to agree with. A profile map edited after the data changed
        # would otherwise cast to a type the column no longer has.
        data_type = data.schema[column_name].dataType

        if isinstance(data_type, StringType):
            # Text keeps its existing trim-both-sides behaviour, so a padded
            # " Retail " still matches a list entry of "Retail".
            comparable = trim(column.cast("string"))
            candidates = [lit(value) for value in valid_values]
        else:
            comparable = column
            candidates = [lit(value).cast(data_type) for value in valid_values]

        # Native column expression instead of a per-row Python UDF: isin() runs entirely in
        # the JVM. An empty valid_values set (a configured-but-empty LOV) is guarded
        # separately - Spark's isin() with no arguments isn't valid SQL - matching the old
        # UDF's behavior of always failing non-null values in that case.
        if valid_values:
            # A list value the column's type cannot represent ("Retail" for a
            # boolean) casts to NULL, and SQL's `x IN (..., NULL)` yields NULL
            # rather than false for a non-match - which would have been read as
            # "not a failure" and passed every unmatched row silently. Folding
            # the unknown to false says what is true: the value is not in the
            # list.
            pass_mask = column.isNull() | coalesce(
                comparable.isin(*candidates),
                lit(False),
            )
        else:
            pass_mask = column.isNull()

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Value must be one of the "
                f"{len(valid_values)} allowed values in "
                f"'{lov_name}' (compared as {data_type.simpleString()})"
            ),
        )
