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
        logger.error("Unsupported validation for rule '%s'", self.rule_id)
        raise NotImplementedError(
            f"Rule '{type(self).__name__}' does not implement validate()."
        )

    def supports_column(
        self,
        data: DataFrame,
        column_name: str,
    ) -> bool:
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
        check = udf(validator, BooleanType())
        return check(col(column_name))
