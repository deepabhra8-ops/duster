"""DQ10: flags rows that duplicate another row across a configured set of columns."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, udf
from pyspark.sql.types import BooleanType

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import RuleResult
from engine.rules.base_rule import BaseRule, log_rule_validation
from engine.rules.rule_parser import RuleParameterParser
from engine.rules.rule_registry import register_rule


@register_rule
class DQ10UniquenessRule(BaseRule):
    """Validates that a configured combination of columns is unique across all rows."""

    rule_id = "DQ10"
    rule_name = "Uniqueness / Duplicate Check"
    dimension = "Uniqueness"
    category = "Uniqueness"

    @log_rule_validation
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Fail rows whose configured column combination duplicates another (non-null) row.

        Duplicate key combinations are found via a small groupBy/count aggregate (an eager
        action, collected to the driver) rather than a Window row-count, then checked per row
        through a UDF. This isn't just a style choice - a Window function's result can't be
        used directly in a filter/WHERE clause ("It is not allowed to use window functions
        inside WHERE clause"), and both rule_executor.py and table_validator.py filter every
        rule's pass_mask against the source data, so a Window-based mask would fail every
        single time a rule invalidated any rows.
        """
        columns = self._get_columns(
            data=data,
            column_name=column_name,
            parameters=parameters,
        )

        if not columns:
            return self.create_not_run_result(
                "No column(s) configured for the uniqueness check - check not run"
            )

        # A row with a null in any of the uniqueness columns is exempt from the check
        # (matches the pandas version's data[columns].isnull().any(axis=1) behavior).
        duplicate_keys = {
            tuple(row[column] for column in columns)
            for row in (
                data.groupBy(*columns)
                .count()
                .filter(col("count") > 1)
                .select(*columns)
                .collect()
            )
        }

        check = udf(_IsNotDuplicate(duplicate_keys), BooleanType())
        pass_mask = check(*[col(column) for column in columns])

        return self.create_result(
            pass_mask=pass_mask,
            notes=(
                f"Combination of {', '.join(columns)} "
                f"must be unique across all rows"
            ),
        )

    @staticmethod
    def _get_columns(
        data: DataFrame,
        column_name: str,
        parameters: str,
    ) -> list[str]:
        """Resolve the configured uniqueness column set, keeping only columns present in the data."""
        params = RuleParameterParser.parse(parameters)

        # A DQ10 rule is attached to a selected profile-map column.  With no
        # parameters, that selected column is the natural single-field key.
        # Analysts only need to enter a parameter when defining a composite
        # key.  Keep the two-position form for existing profile maps.
        columns_raw = (
            params[1]
            if len(params) > 1
            else params[0]
            if params
            else column_name
        )

        configured_columns = [
            column.strip()
            for column in columns_raw.split(",")
            if column.strip()
        ]

        return [
            column
            for column in configured_columns
            if column in data.columns
        ]


class _IsNotDuplicate:
    """Per-row duplicate-key check for DQ10.

    Built as a module-level callable rather than a closure so Spark can pickle
    it: the deployed engine is Cythonised, and a nested `def` there is not a
    types.FunctionType, so cloudpickle falls back to pickling by qualified name
    and fails with "Can't pickle local object". See _RangeCheck in
    engine/rules/dq5_range.py for the full explanation.
    """

    def __init__(self, duplicate_keys: set) -> None:
        self.duplicate_keys = duplicate_keys

    def __call__(self, *values) -> bool:
        # A row with a null anywhere in the key is exempt: a missing key is a
        # completeness problem, which DQ1 reports.
        if any(value is None for value in values):
            return True

        return values not in self.duplicate_keys
