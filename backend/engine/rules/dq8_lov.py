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
        lov_name = RuleParameterParser.get(
            parameters,
            position=0,
            default="",
        )

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

        data_type = data.schema[column_name].dataType

        if isinstance(data_type, StringType):
            comparable = trim(column.cast("string"))
            candidates = [lit(value) for value in valid_values]
        else:
            comparable = column
            candidates = [lit(value).cast(data_type) for value in valid_values]

        if valid_values:
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
