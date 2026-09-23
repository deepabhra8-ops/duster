"""Resolves a DQ rule via RuleRegistry and executes it against one column, converting rule errors into a safe RuleResult."""

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
    """Resolves and runs a single DQ rule against one column, isolating rule-execution errors."""

    @log_and_reraise(logger, "Failed to initialize rule executor")
    def __init__(
        self,
        context: ExecutionContext,
        rule_registry: RuleRegistry,
    ) -> None:
        """Store the execution context and rule registry."""
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
        """Resolve a rule's raw pass_mask for one column, without counting invalid rows yet.

        Returns None if the rule is unregistered or doesn't support this column, a safe
        all-pass result on error, or the rule's own RuleResult otherwise - invalid_count and
        metadata["_total_count"] are left as create_result()'s placeholders. Counting is
        deferred to finalize_counts() so a caller validating many rules against the same table
        (TableValidator) can batch every rule's invalid_count into a single Spark aggregate
        instead of one job per rule.
        """
        # Bound before the try because the except below reports through it: if
        # rule_ids() or get() is what raised, `rule` would otherwise be unbound
        # and the error handler would itself die with UnboundLocalError, turning
        # a safely-recorded per-rule failure into one that kills the whole table.
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
        """Run a single rule against one column and return its fully-counted RuleResult.

        A convenience wrapper around resolve() + finalize_counts() for callers that need just
        one rule's result. TableValidator drives multiple rules through resolve() and a single
        shared finalize_counts() call instead, to batch a whole table's counting into one
        Spark action - see TableValidator._validate().
        """
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
        """Batch-compute invalid_count for every resolved RuleResult in one aggregate pass.

        Each pass_mask is an unevaluated Column predicate over the same `data`, so all of them
        can be counted together in a single `.agg(...)` - one Spark job for N rules instead of
        N. `total_rows` is already known by the caller (TableValidator computes it once for the
        whole table), so it's threaded straight into metadata["_total_count"] rather than
        re-counted per rule.
        """
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
        """Build an all-pass RuleResult carrying the error, since a broken rule can't tell which rows failed.

        invalid_count is always 0 here by construction (pass_mask=lit(True) - nothing can fail
        a mask that's always True), so no count is needed even before finalize_counts() fills
        in metadata["_total_count"].

        `rule` is None when the failure happened before one could be resolved
        (an unregistered id, or a rule class that raised on construction), so
        its metadata is merged only when there is a rule to ask.
        """
        return RuleResult(
            pass_mask=lit(True),
            invalid_count=0,
            notes=f"Rule error: {error}",
            metadata={
                **(dict(rule.metadata()) if rule is not None else {}),
                # A rule that crashed did not judge these rows, so it must not
                # be scored as if every row passed - same reasoning as
                # BaseRule.create_not_run_result.
                STATUS_KEY: STATUS_NOT_RUN,
                "not_run_reason": f"Rule error: {error}",
                "error": str(error),
            },
        )
