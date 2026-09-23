from __future__ import annotations

from dataclasses import replace

from pyspark.sql import DataFrame
from pyspark.sql.functions import count as spark_count, lit, when

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import STATUS_KEY, STATUS_NOT_RUN, RuleResult
from engine.rules.rule_registry import RuleRegistry
from utils.logger import get_logger, log_and_reraise


logger = get_logger(__name__)


class RuleExecutor:
    @log_and_reraise(logger, "Failed to initialize rule executor")
    def __init__(
        self,
        context: ExecutionContext,
        rule_registry: RuleRegistry,
    ) -> None:
        self.context = context
        self.rule_registry = rule_registry
        logger.debug("Initialized rule executor")

    def resolve(
        self,
        rule_id: str,
        data: DataFrame,
        column_name: str,
        parameters: str,
    ) -> RuleResult | None:
        rule = None

        try:
            if rule_id not in self.rule_registry.rule_ids():
                logger.debug("Rule '%s' is not registered", rule_id)
                return None

            rule = self.rule_registry.get(
                rule_id=rule_id,
                context=self.context,
            )

            if not rule.supports_column(
                data=data,
                column_name=column_name,
            ):
                logger.debug(
                    "Rule '%s' does not support column '%s'",
                    rule_id,
                    column_name,
                )
                return None

            rule.validate_configuration(
                parameters
            )

            result = rule.validate(
                data=data,
                column_name=column_name,
                parameters=parameters,
                context=self.context,
            )
            logger.debug(
                "Resolved rule '%s' for column '%s'",
                rule_id,
                column_name,
            )
            return result

        except Exception as exc:
            logger.exception(
                "Rule '%s' failed for column '%s'; returning safe result",
                rule_id,
                column_name,
            )
            return self._build_rule_error_result(
                rule=rule,
                error=exc,
            )

    def execute(
        self,
        rule_id: str,
        data: DataFrame,
        column_name: str,
        parameters: str,
    ) -> RuleResult | None:
        result = self.resolve(
            rule_id=rule_id,
            data=data,
            column_name=column_name,
            parameters=parameters,
        )

        if result is None:
            return None

        return self.finalize_counts(
            results=[result],
            total_rows=data.count(),
            data=data,
        )[0]

    def finalize_counts(
        self,
        results: list[RuleResult],
        total_rows: int,
        data: DataFrame,
    ) -> list[RuleResult]:
        try:
            if not results:
                return []

            counted = data.agg(
                *[
                    spark_count(when(~result.pass_mask, 1)).alias(f"_dq_invalid_{index}")
                    for index, result in enumerate(results)
                ]
            ).first()

            return [
                replace(
                    result,
                    invalid_count=int(counted[f"_dq_invalid_{index}"]),
                    metadata={
                        **result.metadata,
                        "_total_count": total_rows,
                    },
                )
                for index, result in enumerate(results)
            ]
        except Exception:
            logger.exception(
                "Failed to batch-count %s rule result(s)",
                len(results),
            )
            raise

    @log_and_reraise(
        logger,
        lambda self, rule, **_: (
            "Failed to build safe result for rule '%s'",
            getattr(rule, "rule_id", "unknown"),
        ),
    )
    def _build_rule_error_result(
        self,
        rule,
        error: Exception,
    ) -> RuleResult:
        return RuleResult(
            pass_mask=lit(True),
            invalid_count=0,
            notes=f"Rule error: {error}",
            metadata={
                **(dict(rule.metadata()) if rule is not None else {}),
                STATUS_KEY: STATUS_NOT_RUN,
                "not_run_reason": f"Rule error: {error}",
                "error": str(error),
            },
        )
