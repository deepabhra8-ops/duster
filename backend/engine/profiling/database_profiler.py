"""Database table profiler: computes per-column dtype and statistics directly from the Spark DataFrame read for that table."""

from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from sqlalchemy.engine import Engine

from engine.core.result_models import (
    ProfileColumnResult,
    TableProfileResult,
)
from engine.profiling.base_profiler import BaseProfiler
from engine.profiling.profiler_registry import register_profiler
from utils.logger import get_logger


logger = get_logger(__name__)


@register_profiler
class DatabaseProfiler(BaseProfiler):
    """Profiles a database table's columns from the Spark DataFrame already read for it."""

    profiler_type = "database"

    def __init__(
        self,
        context,
        engine: Engine | None = None,
    ) -> None:
        """Store the execution context. The SQLAlchemy engine is accepted for constructor
        compatibility with ProfilerFactory's dependency injection, but is no longer needed -
        profiling now runs directly off the Spark DataFrame passed to profile()."""
        super().__init__(context)
        self.engine = engine

    def profile(
        self,
        data: DataFrame,
        table_config: Mapping[str, Any],
    ) -> TableProfileResult:
        """Profile a database table's columns from its already-read Spark DataFrame."""
        try:
            table_name = str(
                table_config.get(
                    "name",
                    "",
                )
            ).strip()

            if not table_name:
                raise ValueError(
                    "Database table configuration requires a 'name' value."
                )

            rows = self._profile_dataframe(data)

            columns = [
                ProfileColumnResult(
                    column_name=row["column_name"],
                    dtype=row["dtype"],
                    total_count=row["total_count"],
                    null_count=row["null_count"],
                    distinct_count=row["distinct_count"],
                    min_value=row["min_value"],
                    max_value=row["max_value"],
                )
                for row in rows
            ]

            result = TableProfileResult(
                table_name=table_name,
                columns=columns,
            )
            logger.info(
                "Profiled database table '%s' with %s columns",
                table_name,
                len(columns),
            )
            return result
        except Exception:
            logger.exception("Failed to profile database table")
            raise

    def profile_table(
        self,
        schema_name: str,
        table_name: str,
        data: DataFrame | None = None,
    ) -> TableProfileResult:
        """Convenience wrapper to profile a table given its schema/name and already-read data."""
        try:
            if data is None:
                raise ValueError(
                    "DatabaseProfiler.profile_table requires a Spark DataFrame."
                )

            return self.profile(
                data=data,
                table_config={
                    "schema": schema_name,
                    "name": table_name,
                },
            )
        except Exception:
            logger.exception(
                "Failed to profile database table '%s.%s'",
                schema_name,
                table_name,
            )
            raise

    # _profile_dataframe()/_bool_label() live on BaseProfiler now - the aggregate-query
    # logic is generic to any already-read Spark DataFrame, not specific to JDBC sources,
    # and SalesforceProfiler needs the exact same computation.
