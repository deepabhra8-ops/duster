"""Coordinates end-to-end DQ validation: resolves the source, validates each table via TableValidator, stages passed rows, and builds the run result."""

from __future__ import annotations

import itertools
import threading
from typing import Any, Callable, Mapping

from pyspark.sql import DataFrame
from pyspark.sql.functions import current_timestamp

from engine.core.execution_context import ExecutionContext
from engine.core.parallel import resolve_max_workers, run_in_parallel
from engine.core.result_models import (
    TableValidationResult,
    ValidationRunResult,
    DimensionResult,
    ValidationSummary,
)

from engine.data_sources.source_registry import (
    SourceRegistry,
    default_source_registry,
)

from engine.profile_map.profile_map_reader import ProfileMapReader

from engine.rules.rule_registry import (
    RuleRegistry,
    default_rule_registry,
)

from engine.staging.staging_writer_registry import (
    StagingWriterRegistry,
    default_staging_writer_registry,
)

from engine.validation.failure_policy import FailurePolicy
from engine.validation.rule_executor import RuleExecutor
from engine.validation.table_validator import TableValidator
from engine.validation.validation_scorer import ValidationScorer
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)


class ValidationEngine:
    """Orchestrates validation across all configured tables and builds the run-level result."""

    def __init__(
        self,
        context: ExecutionContext,
        source_registry: SourceRegistry | None = None,
        rule_registry: RuleRegistry | None = None,
        staging_registry: StagingWriterRegistry | None = None,
        profile_map_reader: ProfileMapReader | None = None,
        table_validator: TableValidator | None = None,
        rule_executor: RuleExecutor | None = None,
        validation_scorer: ValidationScorer | None = None,
        failure_policy: FailurePolicy | None = None,
    ) -> None:
        """Wire up the engine's collaborators, defaulting to the shared registries."""
        try:
            self.context = context

            self.source_registry = source_registry or default_source_registry
            self.rule_registry = rule_registry or default_rule_registry
            self.staging_registry = staging_registry or default_staging_writer_registry
            self.profile_map_reader = profile_map_reader or ProfileMapReader()
            self.rule_executor = rule_executor or RuleExecutor(
                context=self.context,
                rule_registry=self.rule_registry,
            )
            self.validation_scorer = validation_scorer or ValidationScorer(
                context=self.context,
                rule_registry=self.rule_registry,
            )
            self.failure_policy = failure_policy or FailurePolicy()
            self.table_validator = table_validator or TableValidator(
                context=self.context,
                rule_executor=self.rule_executor,
                validation_scorer=self.validation_scorer,
                failure_policy=self.failure_policy,
            )
            logger.debug("Initialized validation engine")
        except Exception:
            logger.exception("Failed to initialize validation engine")
            raise

    def validate(
        self,
        tables: list[Mapping[str, Any]] | None = None,
        profile_map: Mapping[str, Any] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ValidationRunResult:
        """Validate the configured tables and return the run-level result, reporting progress per table."""
        try:
            return self._validate(
                tables=tables,
                profile_map=profile_map,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        except Exception:
            logger.exception("Validation workflow failed")
            raise

    def _validate(
        self,
        tables: list[Mapping[str, Any]] | None,
        profile_map: Mapping[str, Any] | None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ValidationRunResult:
        """Validate each table (skipping/reading errors gracefully), stage passed rows, and aggregate scores."""
        profile_map = (
            profile_map
            if profile_map is not None
            else self._load_profile_map()
        )

        source = self.source_registry.get(
            source_type=self.context.source_type,
            config=self.context.source_config,
            context=self.context,
        )

        table_configs = (
            tables
            if tables is not None
            else self.context.source_config.get(
                "tables",
                [],
            )
        )

        table_results: dict[
            str,
            TableValidationResult,
        ] = {}

        dimension_scores: dict[
            str,
            list[float],
        ] = {}

        total_tables = len(table_configs)
        completed = itertools.count(1)
        progress_lock = threading.Lock()

        def validate_one(table_config: Mapping[str, Any]):
            """Validate one table. Runs on a worker thread when several overlap."""
            self._check_not_cancelled(cancel_event)

            try:
                return self._validate_one_table(
                    table_config=table_config,
                    source=source,
                    profile_map=profile_map,
                )
            finally:
                if progress_callback is not None:
                    # Tables no longer finish in order, so progress counts how
                    # many are done rather than which index this was. The lock
                    # guards the callback itself - it writes to Postgres, and
                    # two threads calling it at once would interleave.
                    with progress_lock:
                        progress_callback(next(completed), total_tables)

        outcomes = run_in_parallel(
            table_configs,
            validate_one,
            max_workers=resolve_max_workers(self.context.config),
            cancel_event=cancel_event,
            description="table validation",
        )

        # Merged on this thread, in the input's order, so dimension scores are
        # accumulated deterministically no matter what order the tables finished.
        for outcome in outcomes:
            if outcome.error is not None:
                if isinstance(outcome.error, JobCancelledError):
                    raise outcome.error

                logger.exception(
                    "Validation failed for table '%s'",
                    self._get_table_name(outcome.item),
                    exc_info=outcome.error,
                )
                raise outcome.error

            table_name, table_result, table_dimension_scores = outcome.value

            if table_result is not None:
                table_results[table_name] = table_result

            for dimension, scores in table_dimension_scores.items():
                dimension_scores.setdefault(dimension, []).extend(scores)

        # Catch cancellation requested during/after the last table, before the
        # (potentially non-trivial) result-building and report-writing that follow.
        self._check_not_cancelled(cancel_event)

        result = self._build_run_result(
            table_results=table_results,
            dimension_scores=dimension_scores,
        )
        logger.info("Validation completed for %s tables", len(table_results))
        return result

    @staticmethod
    def _check_not_cancelled(
        cancel_event: threading.Event | None,
    ) -> None:
        """Raise JobCancelledError if the caller has signalled cancellation."""
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelledError("Job cancelled by user")

    def _validate_one_table(
        self,
        table_config: Mapping[str, Any],
        source: Any,
        profile_map: Mapping[str, Any],
    ) -> tuple[str, TableValidationResult | None, dict[str, list[float]]]:
        """Validate one table, returning its name, result, and dimension scores.

        Returns rather than writing into shared dicts because tables are
        validated concurrently: two threads appending to one dimension_scores
        list would interleave, and the caller merges these per-table scores on a
        single thread instead. A None result means the table was skipped.
        """
        table_name = self._get_table_name(table_config)
        dimension_scores: dict[str, list[float]] = {}

        if table_name not in profile_map:
            # Silence here is dangerous: every table skipped means an empty run
            # result, which scores as "no data" and reaches the UI looking exactly
            # like a successful validation that simply found nothing wrong. Name
            # the mismatch so the job log says why nothing was validated.
            logger.warning(
                "Skipping table '%s': no profile-map entry for it. "
                "The profile map covers: %s",
                table_name,
                ", ".join(sorted(profile_map)) or "(nothing)",
            )
            return table_name, None, dimension_scores

        data = self._read_table(source=source, table_config=table_config, table_name=table_name)
        if data is None:
            return table_name, None, dimension_scores

        table_result = self.table_validator.validate(
            table_name=table_name,
            data=data,
            table_configuration=profile_map[table_name],
            dimension_scores=dimension_scores,
        )

        if self.context.is_curation_mode:
            self._write_staging(
                table_name=table_name,
                data=table_result.passed_rows,
            )

        return table_name, table_result, dimension_scores

    @staticmethod
    def _read_table(
        source: Any,
        table_config: Mapping[str, Any],
        table_name: str,
    ) -> DataFrame | None:
        """Read a table from the source, returning None (and logging) if it can't be read."""
        try:
            return source.read(table_config=table_config)
        except FileNotFoundError:
            logger.warning("Source file not found for table '%s'", table_name)
            return None
        except Exception:
            logger.exception("Failed to read source table '%s'", table_name)
            return None

    def validate_table(
        self,
        table_name: str,
        data: DataFrame,
        table_configuration: Any,
    ) -> TableValidationResult:
        """Validate a single in-memory table."""
        dimension_scores: dict[
            str,
            list[float],
        ] = {}

        try:
            return self.table_validator.validate(
                table_name=table_name,
                data=data,
                table_configuration=table_configuration,
                dimension_scores=dimension_scores,
            )
        except Exception:
            logger.exception("Failed to validate table '%s'", table_name)
            raise

    def _write_staging(
        self,
        table_name: str,
        data: DataFrame,
    ) -> None:
        """Write a table's passed rows to the configured staging destination."""
        # TableValidator tags rows with an internal _dq_row_id column for row-failure
        # tracking; strip it before it reaches the curated staging output.
        if "_dq_row_id" in data.columns:
            data = data.drop("_dq_row_id")

        staging_config = self.context.staging_config

        staging_type = str(
            staging_config.get(
                "type",
                "csv",
            )
        ).strip().lower()

        writer = self.staging_registry.get(
            staging_type=staging_type,
            context=self.context,
        )

        writer.validate_configuration(
            staging_config
        )

        try:
            writer.write(
                table_name=table_name,
                data=self._add_curated_timestamp(data),
                staging_config=staging_config,
            )
            logger.info("Wrote staged data for table '%s'", table_name)
        except Exception:
            logger.exception("Failed to stage table '%s'", table_name)
            raise

    def _load_profile_map(
        self,
    ) -> Mapping[str, Any]:
        """Load the profile map configured for the current execution."""
        path = self.context.config.get(
            "profile_map_file",
            "",
        )

        if not path:
            return {}

        try:
            result = self.profile_map_reader.read(path)
            logger.debug("Loaded profile map '%s'", path)
            return result
        except Exception:
            logger.exception("Failed to load profile map '%s'", path)
            raise

    def _build_run_result(
        self,
        table_results: Mapping[
            str,
            TableValidationResult,
        ],
        dimension_scores: Mapping[
            str,
            list[float],
        ],
    ) -> ValidationRunResult:
        """Aggregate per-table results and dimension scores into the final ValidationRunResult."""
        dimension_results = {
            dimension: DimensionResult.from_scores(
                dimension=dimension,
                scores=values,
            )
            for dimension, values in dimension_scores.items()
        }

        summary = ValidationSummary.from_dimensions(
            dimension_results=dimension_results,
        )

        result = ValidationRunResult(
            project_name=self.context.project_name,
            run_timestamp=self.context.run_timestamp,
            summary=summary,
            tables=dict(table_results),
        )
        logger.debug("Built validation run result for %s tables", len(table_results))
        return result

    @staticmethod
    def _add_curated_timestamp(
        data: DataFrame,
    ) -> DataFrame:
        """Return the data with a curated_at timestamp column added."""
        return data.withColumn(
            "curated_at",
            current_timestamp(),
        )

    @staticmethod
    def _get_table_name(
        table_config: Mapping[str, Any],
    ) -> str:
        """Resolve a table's name from its config (name, then table, then file)."""
        table_name = str(
            table_config.get(
                "name",
                table_config.get(
                    "table",
                    table_config.get(
                        "file",
                        "",
                    ),
                ),
            )
        ).strip()

        if not table_name:
            raise ValueError(
                "Table configuration requires a "
                "'name', 'table', or 'file' value."
            )

        return table_name
