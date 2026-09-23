"""Orchestrates profiling: resolves the data source, profiles each table, infers rules, and builds the profile map."""

from __future__ import annotations

import itertools
import threading
from typing import Any, Callable, Mapping

from engine.core.execution_context import ExecutionContext
from engine.core.parallel import resolve_max_workers, run_in_parallel
from engine.core.result_models import ProfileRunResult
from engine.data_sources.source_registry import (
    SourceRegistry,
    default_source_registry,
)
from engine.profiling.profiler_factory import ProfilerFactory
from engine.profiling.profiler_registry import (
    ProfilerRegistry,
    default_profiler_registry,
)
from engine.profiling.rule_inference import RuleInference
from engine.profile_map.profile_map_builder import ProfileMapBuilder
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfilingEngine:
    """Coordinates profiling, rule inference, and profile-map building for a source."""

    def __init__(
        self,
        context: ExecutionContext,
        source_registry: SourceRegistry | None = None,
        profiler_registry: ProfilerRegistry | None = None,
        profiler_factory: ProfilerFactory | None = None,
        rule_inference: RuleInference | None = None,
        profile_map_builder: ProfileMapBuilder | None = None,
    ) -> None:
        """Wire up the engine's collaborators, defaulting to the shared registries."""
        try:
            self.context = context

            self.source_registry = (
                source_registry
                or default_source_registry
            )

            self.profiler_registry = (
                profiler_registry
                or default_profiler_registry
            )

            self.profiler_factory = (
                profiler_factory
                or ProfilerFactory(
                    registry=self.profiler_registry,
                )
            )

            self.rule_inference = (
                rule_inference
                or RuleInference()
            )

            self.profile_map_builder = (
                profile_map_builder
                or ProfileMapBuilder()
            )
            logger.debug(
                "Initialized profiling engine for project '%s'",
                context.project_name,
            )
        except Exception:
            logger.exception("Failed to initialize profiling engine")
            raise

    def profile(
        self,
        tables: list[Mapping[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ProfileRunResult:
        """Profile each configured table, reporting progress after each one."""
        try:
            source_type = self.context.source_type

            source = self.source_registry.get(
                source_type=source_type,
                config=self.context.source_config,
                context=self.context,
            )

            profiler = self.profiler_factory.create(
                profiler_type=source_type,
                context=self.context,
                source=source,
            )

            total_tables = len(tables)
            completed = itertools.count(1)
            progress_lock = threading.Lock()

            def profile_one(table_config: Mapping[str, Any]):
                """Profile one table. Runs on a worker thread when several overlap."""
                if cancel_event is not None and cancel_event.is_set():
                    raise JobCancelledError("Job cancelled by user")

                try:
                    data = source.read(
                        table_config=table_config,
                    )
                    # Profiling runs one aggregate query per column; without caching, each of
                    # those actions would re-read/re-parse the source from scratch.
                    data = data.cache()

                    try:
                        profile = profiler.profile(
                            data=data,
                            table_config=table_config,
                        )
                    finally:
                        data.unpersist()

                    profile.metadata.update(
                        {
                            "source_type": source_type,
                            "table_config": dict(
                                table_config
                            ),
                        }
                    )

                    return profile
                finally:
                    # A table that failed still counts as finished, so the bar
                    # reaches N of N when the others are kept.
                    if progress_callback is not None:
                        # Tables no longer finish in order, so progress counts how
                        # many are done rather than which index this was. The lock
                        # guards the callback itself - it writes to Postgres, and
                        # two threads calling it at once would interleave.
                        with progress_lock:
                            progress_callback(next(completed), total_tables)

            outcomes = run_in_parallel(
                tables,
                profile_one,
                max_workers=resolve_max_workers(self.context.config),
                cancel_event=cancel_event,
                description="table profile",
            )

            tables_result = {}
            failed_tables: dict[str, str] = {}
            first_error: BaseException | None = None

            for outcome in outcomes:
                table_name = self._get_table_name(outcome.item)

                if outcome.error is not None:
                    # A cancellation is the whole run ending, not one table
                    # failing, so it propagates; anything else is recorded
                    # against its table and the other tables' work is kept.
                    if isinstance(outcome.error, JobCancelledError):
                        raise outcome.error

                    logger.exception(
                        "Profiling failed for table '%s'",
                        table_name,
                        exc_info=outcome.error,
                    )
                    failed_tables[table_name] = self._short_error(outcome.error)
                    first_error = first_error or outcome.error
                    continue

                tables_result[table_name] = outcome.value
                logger.debug("Profiled table '%s'", table_name)

            # Nothing survived, so there is no partial result worth keeping - fail
            # the run the way a single-table run always has.
            if first_error is not None and not tables_result:
                raise first_error

            result = ProfileRunResult(
                project_name=self.context.project_name,
                run_timestamp=self.context.run_timestamp,
                tables=tables_result,
                failed_tables=failed_tables,
            )
            logger.info(
                "Profiling completed for %s tables (%s failed)",
                len(tables_result),
                len(failed_tables),
            )
            return result
        except Exception:
            logger.exception("Profiling workflow failed")
            raise

    def profile_table(
        self,
        table_config: Mapping[str, Any],
    ):
        """Profile a single table and return its result."""
        try:
            result = self.profile(
                tables=[table_config]
            )

            table_name = self._get_table_name(
                table_config
            )

            return result.tables[table_name]
        except Exception:
            logger.exception("Failed to profile a single table")
            raise

    def infer_rules(
        self,
        profile_result: ProfileRunResult,
    ) -> dict[str, dict[str, list[str]]]:
        """Infer rule IDs for every column of every profiled table, from its already-computed profile stats.

        Rule inference only needs each column's name and dtype - both already sitting in
        ``profile_result`` from the profiling pass that just ran - so this reads no
        DataFrame at all rather than re-reading each table's source a second time.
        """
        try:
            inferred_rules: dict[
                str,
                dict[str, list[str]],
            ] = {}

            for table_name, table_profile in (
                profile_result.tables.items()
            ):
                inferred_rules[table_name] = {
                    column.column_name: (
                        self.rule_inference.infer_from_profile(
                            column_name=column.column_name,
                            dtype=column.dtype,
                        )
                    )
                    for column in table_profile.columns
                }

            logger.info("Inferred rules for %s tables", len(inferred_rules))
            return inferred_rules
        except Exception:
            logger.exception("Rule inference workflow failed")
            raise

    def build_profile_map(
        self,
        profile_result: ProfileRunResult,
        inferred_rules: Mapping[
            str,
            Mapping[str, list[str]],
        ] | None = None,
    ):
        """Build the profile map from a profiling result and its inferred rules."""
        try:
            result = self.profile_map_builder.build(
                profile_result=profile_result,
                inferred_rules=inferred_rules,
            )
            logger.info("Built profile map for %s tables", len(result))
            return result
        except Exception:
            logger.exception("Profile-map build workflow failed")
            raise

    def profile_and_build_map(
        self,
        tables: list[Mapping[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ):
        """Run profiling, rule inference, and profile-map building end to end."""
        try:
            profile_result = self.profile(
                tables=tables,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )

            # Catch cancellation requested during/after the last table, before rule
            # inference and profile-map building (and its write to disk) run.
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelledError("Job cancelled by user")

            # infer_rules() reads directly from profile_result's already-computed column
            # stats - no second read of the source is needed here.
            inferred_rules = self.infer_rules(
                profile_result=profile_result,
            )

            profile_map = self.build_profile_map(
                profile_result=profile_result,
                inferred_rules=inferred_rules,
            )

            logger.info("Profiling and profile-map build completed")
            return profile_result, profile_map
        except Exception:
            logger.exception("Profiling and profile-map workflow failed")
            raise

    @staticmethod
    def _short_error(error: BaseException) -> str:
        """First line of an error, capped - Spark messages can run to a full stack."""
        lines = [line.strip() for line in str(error).splitlines() if line.strip()]
        message = lines[0] if lines else type(error).__name__
        return message[:300]

    @staticmethod
    def _get_table_name(
        table_config: Mapping[str, Any],
    ) -> str:
        """Resolve a table's name from its config (name, then table, then file)."""
        try:
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
                ),
            ).strip()

            if not table_name:
                raise ValueError(
                    "Table configuration requires a "
                    "'name', 'table', or 'file' value."
                )

            return table_name
        except Exception:
            logger.exception("Failed to resolve table name")
            raise
