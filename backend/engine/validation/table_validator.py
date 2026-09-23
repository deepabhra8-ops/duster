"""Validates one table: runs every configured rule per column, records failures/scores, and splits rows into passed/failed."""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from typing import Any

from pyspark.sql import Column, DataFrame
from pyspark.sql.functions import col, lit, monotonically_increasing_id

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import (
    RowFailure,
    RuleExecutionDetail,
    RuleResult,
    TableValidationResult,
)
from engine.validation.failure_policy import FailurePolicy
from engine.validation.rule_executor import RuleExecutor
from engine.validation.validation_scorer import ValidationScorer
from utils.logger import get_logger


logger = get_logger(__name__)


ROW_ID_COLUMN = "_dq_row_id"


@dataclass(frozen=True)
class _PendingRule:
    """One resolved (column, rule) pair, awaiting its batched invalid_count."""

    column_configuration: Any
    column_name: str
    rule_id: str
    result: RuleResult


class TableValidator:
    """Runs configured rules against one table's columns and builds its TableValidationResult."""

    def __init__(
        self,
        context: ExecutionContext,
        rule_executor: RuleExecutor,
        validation_scorer: ValidationScorer,
        failure_policy: FailurePolicy,
    ) -> None:
        """Store the execution context and validation collaborators."""
        try:
            self.context = context
            self.rule_executor = rule_executor
            self.validation_scorer = validation_scorer
            self.failure_policy = failure_policy

            logger.debug(
                "Initialized table validator"
            )
        except Exception:
            logger.exception(
                "Failed to initialize table validator"
            )
            raise

    def validate(
        self,
        table_name: str,
        data: DataFrame,
        table_configuration: Any,
        dimension_scores: dict[
            str,
            list[float],
        ]
        | None = None,
    ) -> TableValidationResult:
        """Validate a table's data against its configured rules."""
        try:
            return self._validate(
                table_name=table_name,
                data=data,
                table_configuration=table_configuration,
                dimension_scores=dimension_scores,
            )
        except Exception:
            logger.exception(
                "Failed to validate table '%s'",
                table_name,
            )
            raise

    def _validate(
        self,
        table_name: str,
        data: DataFrame,
        table_configuration: Any,
        dimension_scores: dict[
            str,
            list[float],
        ]
        | None,
    ) -> TableValidationResult:
        """Run every configured rule per column, accumulating failures, scores, and rule details.

        Runs in three phases instead of one action per rule: resolve every rule's raw
        pass_mask first (no counting), batch-count all of them in a single aggregate pass,
        then fold the now-counted results into fail_mask/rule_details/scores and collect
        every rule's failing rows in one more batched pass (see _collect_row_failures()).
        """

        # Tag each row with a stable id up front - so failures from different rules on the
        # same row line up under one key in _collect_row_failures() - and cache the result,
        # so the several actions below (finalize_counts()'s aggregate, the row-failure
        # collect, and _build_result()'s counts) don't each re-read/re-parse the source from
        # scratch. The cache is released by the caller (DQValidator.run()) once report
        # writing has finished reading passed_rows/failed_rows from the result below.
        data = data.withColumn(
            ROW_ID_COLUMN,
            monotonically_increasing_id(),
        ).cache()

        total_rows = data.count()

        pending = self._resolve_rules(
            data=data,
            table_configuration=table_configuration,
        )

        # One Spark aggregate for every rule's invalid_count on this table, instead of one
        # action per rule.
        results = self.rule_executor.finalize_counts(
            results=[entry.result for entry in pending],
            total_rows=total_rows,
            data=data,
        )

        fail_mask: Column = lit(False)

        rule_details: list[
            RuleExecutionDetail
        ] = []

        annotated: list[
            tuple[_PendingRule, RuleResult, str, str]
        ] = []

        for entry, result in zip(pending, results):
            fail_mask, dimension, category = self._finalize_rule(
                table_name=table_name,
                entry=entry,
                result=result,
                total_rows=total_rows,
                fail_mask=fail_mask,
                rule_details=rule_details,
                dimension_scores=dimension_scores,
            )

            annotated.append(
                (entry, result, dimension, category)
            )

        # One filter + select + collect for every rule's failing rows on this table,
        # instead of one per rule - see _collect_row_failures().
        row_failures = self._collect_row_failures(
            data=data,
            annotated=annotated,
        )

        return self._build_result(
            table_name=table_name,
            total_rows=total_rows,
            fail_mask=fail_mask,
            rule_details=rule_details,
            row_failures=row_failures,
            data=data,
        )

    def _resolve_rules(
        self,
        data: DataFrame,
        table_configuration: Any,
    ) -> list[_PendingRule]:
        """Resolve every configured rule's raw pass_mask for every column, without counting yet."""

        pending: list[_PendingRule] = []

        for column_configuration in (
            table_configuration.columns
        ):
            column_name = str(
                column_configuration.column_name
            ).strip()

            rule_ids = (
                column_configuration.rule_ids
            )

            if not column_name or not rule_ids:
                continue

            for rule_id in rule_ids:
                rule_id = str(rule_id).strip()

                if not rule_id:
                    continue

                result = self.rule_executor.resolve(
                    rule_id=rule_id,
                    data=data,
                    column_name=column_name,
                    parameters=(
                        column_configuration.parameters
                    ),
                )

                if result is None:
                    continue

                pending.append(
                    _PendingRule(
                        column_configuration=column_configuration,
                        column_name=column_name,
                        rule_id=rule_id,
                        result=result,
                    )
                )

        return pending

    def _finalize_rule(
        self,
        table_name: str,
        entry: _PendingRule,
        result: RuleResult,
        total_rows: int,
        fail_mask: Column,
        rule_details: list[RuleExecutionDetail],
        dimension_scores: dict[
            str,
            list[float],
        ]
        | None,
    ) -> tuple[Column, str, str]:
        """Fold one rule's already-counted result into scores/details, returning the updated fail
        mask plus its dimension/category (reused by _collect_row_failures() so they aren't
        resolved twice)."""

        dimension = self._resolve_dimension(
            rule_id=entry.rule_id,
        )

        category = self._resolve_category(
            rule_id=entry.rule_id,
        )

        rule_details.append(
            self._build_rule_detail(
                table_name=table_name,
                column_configuration=(
                    entry.column_configuration
                ),
                rule_id=entry.rule_id,
                dimension=dimension,
                result=result,
            )
        )

        invalid_mask = ~result.pass_mask

        # A rule that could not run is deliberately not scored. Its pass_mask is
        # all-true by construction, so recording it would average a perfect 1.0
        # into the dimension and report "we could not check this" as flawless
        # data quality - see BaseRule.create_not_run_result.
        if dimension_scores is not None and result.was_run:
            self._record_score(
                invalid_count=result.invalid_count,
                total_rows=total_rows,
                dimension=dimension,
                dimension_scores=(
                    dimension_scores
                ),
            )

        if self.failure_policy.should_propagate(
            rule_id=entry.rule_id,
        ):
            return fail_mask | invalid_mask, dimension, category

        return fail_mask, dimension, category

    @staticmethod
    def _build_result(
        table_name: str,
        total_rows: int,
        fail_mask: Column,
        rule_details: list[RuleExecutionDetail],
        row_failures: dict[
            Any,
            list[RowFailure],
        ],
        data: DataFrame,
    ) -> TableValidationResult:
        """Assemble the TableValidationResult from the accumulated masks, details, and failures."""

        pass_mask = ~fail_mask

        passed_rows = data.filter(pass_mask)
        failed_rows = data.filter(fail_mask)

        failed_row_count = failed_rows.count()
        passed_row_count = passed_rows.count()

        result = TableValidationResult(
            table_name=table_name,
            total_rows=total_rows,
            pass_mask=pass_mask,
            rule_details=rule_details,
            passed_rows=passed_rows,
            failed_rows=failed_rows,
            row_failures=row_failures,
            metadata={
                "rule_count": len(
                    rule_details
                ),
                "failed_row_count": failed_row_count,
                "passed_row_count": passed_row_count,
                # Kept so the caller can unpersist this table's cache once every
                # consumer (staging write, row-failure collection above, and report
                # writing, which reads passed_rows/failed_rows after validate()
                # returns) is done with it - see DQValidator.run().
                "_cached_source": data,
            },
        )

        logger.info(
            "Validated table '%s': %s rows, "
            "%s failed rows, %s rules",
            table_name,
            total_rows,
            result.fail_count,
            len(rule_details),
        )

        return result

    def _resolve_dimension(
        self,
        rule_id: str,
    ) -> str:
        """Resolve a rule's DQ dimension."""
        return self.validation_scorer.get_dimension(
            rule_id=rule_id,
            context=self.context,
        )

    def _resolve_category(
        self,
        rule_id: str,
    ) -> str:
        """Resolve a rule's category."""
        return self.validation_scorer.get_category(
            rule_id=rule_id,
            context=self.context,
        )

    def _record_score(
        self,
        invalid_count: int,
        total_rows: int,
        dimension: str,
        dimension_scores: dict[
            str,
            list[float],
        ],
    ) -> None:
        """Calculate and append this rule's score to its dimension's score list."""

        score = (
            self.validation_scorer.calculate_rule_score(
                total_rows=total_rows,
                invalid_count=invalid_count,
            )
        )

        dimension_scores.setdefault(
            dimension,
            [],
        ).append(score)

    @staticmethod
    def _collect_row_failures(
        data: DataFrame,
        annotated: list[
            tuple[_PendingRule, RuleResult, str, str]
        ],
    ) -> dict[Any, list[RowFailure]]:
        """Collect every rule's failing rows in one filter + select + collect, instead of one per rule.

        Each rule's invalid mask is a known Column predicate before any action runs - same as
        RuleExecutor.finalize_counts() batching invalid_count into a single .agg() - so this
        tags every row with a per-rule invalid flag, filters down to rows any rule invalidated,
        and collects once regardless of how many rules ran.
        """

        considered = [
            (entry, result, dimension, category)
            for entry, result, dimension, category in annotated
            if entry.column_name in data.columns
        ]

        if not considered:
            return {}

        invalid_masks = [
            ~result.pass_mask
            for _, result, _, _ in considered
        ]

        flag_aliases = [
            f"_dq_rowfail_{index}"
            for index in range(len(considered))
        ]

        # Rules can repeat a column, so only select each one once.
        column_names = list(
            dict.fromkeys(
                entry.column_name
                for entry, _, _, _ in considered
            )
        )

        select_exprs = (
            [col(ROW_ID_COLUMN)]
            + [col(name) for name in column_names]
            + [
                mask.alias(alias)
                for mask, alias in zip(invalid_masks, flag_aliases)
            ]
        )

        any_invalid = reduce(
            lambda left, right: left | right,
            invalid_masks,
        )

        rows = (
            data
            .filter(any_invalid)
            .select(*select_exprs)
            .collect()
        )

        row_failures: dict[Any, list[RowFailure]] = {}

        for row in rows:
            row_index = row[ROW_ID_COLUMN]

            for (entry, result, dimension, category), alias in zip(
                considered,
                flag_aliases,
            ):
                if not row[alias]:
                    continue

                failure = RowFailure(
                    column_name=entry.column_name,
                    rule_id=entry.rule_id,
                    notes=result.notes,
                    failed_value=row[entry.column_name],
                    dimension=dimension,
                    category=category,
                )

                row_failures.setdefault(
                    row_index,
                    [],
                ).append(
                    failure
                )

        return row_failures

    @staticmethod
    def _build_rule_detail(
        table_name: str,
        column_configuration: Any,
        rule_id: str,
        dimension: str,
        result: RuleResult,
    ) -> RuleExecutionDetail:
        """Build a RuleExecutionDetail summarizing one rule's execution against one column."""

        return RuleExecutionDetail.from_rule_result(
            table_name=table_name,
            column_name=(
                column_configuration.column_name
            ),
            rule_id=rule_id,
            dimension=dimension,
            cde=bool(
                column_configuration.cde
            ),
            result=result,
        )
