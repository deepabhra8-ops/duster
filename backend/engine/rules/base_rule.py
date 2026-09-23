"""Defines the BaseRule contract every DQ rule implements, plus the log_rule_validation decorator and result-building helper."""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable, Mapping

from pyspark.sql import Column, DataFrame
from pyspark.sql.functions import col, lit, udf
from pyspark.sql.types import BooleanType

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import STATUS_KEY, STATUS_NOT_RUN, RuleResult
from utils.logger import get_logger


logger = get_logger(__name__)


def log_rule_validation(method):
    """Decorator: log a rule's validation failures while preserving its call signature."""

    @wraps(method)
    def wrapped(self, data, column_name, parameters, context):
        try:
            result = method(
                self,
                data,
                column_name,
                parameters,
                context,
            )
            logger.debug(
                "Rule '%s' validated column '%s'",
                self.rule_id,
                column_name,
            )
            return result
        except Exception:
            logger.exception(
                "Rule '%s' failed for column '%s'",
                self.rule_id,
                column_name,
            )
            raise

    return wrapped


class BaseRule(ABC):
    """Base class for a DQ rule that validates one column and returns a RuleResult."""

    rule_id: str = ""
    rule_name: str = ""
    dimension: str = "Other"
    category: str = "Other"

    @abstractmethod
    def validate(
        self,
        data: DataFrame,
        column_name: str,
        parameters: str,
        context: ExecutionContext,
    ) -> RuleResult:
        """Validate one column against this rule; implemented by each rule."""
        logger.error("Unsupported validation for rule '%s'", self.rule_id)
        raise NotImplementedError(
            f"Rule '{type(self).__name__}' does not implement validate()."
        )

    def supports_column(
        self,
        data: DataFrame,
        column_name: str,
    ) -> bool:
        """Return whether the column exists in the data."""
        try:
            supported = column_name in data.columns
            logger.debug(
                "Rule '%s' column support check for '%s': %s",
                self.rule_id,
                column_name,
                supported,
            )
            return supported
        except Exception:
            logger.exception(
                "Failed to check column support for rule '%s'",
                self.rule_id,
            )
            raise

    def validate_configuration(
        self,
        parameters: str,
    ) -> None:
        """Validate rule-specific parameters; no-op by default."""
        try:
            logger.debug(
                "No base configuration validation required for rule '%s'",
                self.rule_id,
            )
        except Exception:
            logger.exception(
                "Failed to validate configuration for rule '%s'",
                self.rule_id,
            )
            raise

    def metadata(self) -> Mapping[str, Any]:
        """Return descriptive metadata about this rule."""
        try:
            return {
                "rule_id": self.rule_id,
                "rule_name": self.rule_name,
                "dimension": self.dimension,
                "category": self.category,
            }
        except Exception:
            logger.exception("Failed to generate metadata for rule '%s'", self.rule_id)
            raise

    def create_result(
        self,
        pass_mask: Column,
        notes: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuleResult:
        """Build a RuleResult from a pass mask predicate.

        Unlike the pandas version, ``invalid_count`` can't be computed here - ``pass_mask``
        is an unevaluated Spark ``Column`` with no ``data`` to filter against. It's set to 0
        as a placeholder; ``RuleExecutor`` fills in the real count (and ``_total_count``)
        right after calling ``validate()``, which is the one place that has both the mask and
        the DataFrame it applies to.
        """
        try:
            result = RuleResult(
                pass_mask=pass_mask,
                invalid_count=0,
                notes=notes,
                metadata={
                    **self.metadata(),
                    **(metadata or {}),
                },
            )
            logger.debug(
                "Created result for rule '%s'",
                self.rule_id,
            )
            return result
        except Exception:
            logger.exception("Failed to create result for rule '%s'", self.rule_id)
            raise

    def create_not_run_result(
        self,
        reason: str,
    ) -> RuleResult:
        """Build a result for a check that could not be performed at all.

        Distinct from a check that ran and found nothing wrong. Rules used to
        express "I have no reference list / no configured columns / an
        unparseable expression" by returning an all-pass mask, which the scorer
        then averaged in as a perfect 1.0 - so a misconfigured check reported
        as flawless data quality. That is the most damaging thing this product
        can do, and STATUS_NOT_RUN is what lets the scorer exclude it and the
        UI label it instead.

        The mask stays all-pass because the rows genuinely cannot be judged:
        anything else would invent failures. Only the status distinguishes it.
        """
        return self.create_result(
            pass_mask=lit(True),
            notes=reason,
            metadata={
                STATUS_KEY: STATUS_NOT_RUN,
                "not_run_reason": reason,
            },
        )

    @staticmethod
    def value_mask(
        data: DataFrame,
        column_name: str,
        validator: Callable[[Any], bool],
    ) -> Column:
        """Wrap a per-value Python predicate as a Spark Column, for rules whose logic isn't
        easily expressed as native Spark functions."""
        check = udf(validator, BooleanType())
        return check(col(column_name))
