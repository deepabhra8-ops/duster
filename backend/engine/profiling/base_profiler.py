"""Defines the BaseProfiler contract shared by all table profiling implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, count, countDistinct, max as spark_max, min as spark_min, when

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import TableProfileResult
from engine.profiling.dtype_utils import NOT_APPLICABLE, is_string_dtype, is_boolean_dtype
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseProfiler(ABC):
    """Base class for a profiler that produces a TableProfileResult for a table."""

    profiler_type: str = ""

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
        """Store the execution context."""
        try:
            self.context = context
            logger.debug(
                "Initialized %s for profiler type '%s'",
                type(self).__name__,
                self.profiler_type,
            )
        except Exception:
            logger.exception(
                "Failed to initialize %s for profiler type '%s'",
                type(self).__name__,
                self.profiler_type,
            )
            raise

    @abstractmethod
    def profile(
        self,
        data: DataFrame,
        table_config: Mapping[str, Any],
    ) -> TableProfileResult:
        """Profile a table's data; implemented by each profiler type."""
        logger.error(
            "Unsupported profile operation for profiler type '%s'",
            self.profiler_type,
        )
        raise NotImplementedError(
            f"Profiler '{type(self).__name__}' does not implement profile()."
        )

    def supports(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        """Return whether this profiler supports the given table config; True by default."""
        try:
            logger.debug(
                "Default profiler support check passed for type '%s'",
                self.profiler_type,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to check support for profiler type '%s'",
                self.profiler_type,
            )
            raise

    def validate_configuration(
        self,
        table_config: Mapping[str, Any],
    ) -> None:
        """Validate profiler-specific configuration; no-op by default."""
        try:
            logger.debug(
                "No base configuration validation required for profiler type '%s'",
                self.profiler_type,
            )
        except Exception:
            logger.exception(
                "Failed to validate configuration for profiler type '%s'",
                self.profiler_type,
            )
            raise

    def _profile_dataframe(
        self,
        data: DataFrame,
    ) -> list[dict[str, Any]]:
        """Compute every column's dtype and statistics via one combined aggregate query.

        Shared by every profiler that profiles an already-read Spark DataFrame (database,
        Salesforce, ...) rather than issuing a separate `.select(...).first()` per column -
        each a distinct Spark action that, without a cache sitting in front of it, re-reads
        the source from scratch. A 50-column table meant up to 51 scans (1 for the row count,
        50 for the per-column stats) instead of 1. Building one list of aliased aggregate
        expressions and running it through a single `.select(*exprs).first()` computes every
        column's stats - and the row count - in a single pass, regardless of column count.
        """
        try:
            fields = list(data.schema.fields)

            if not fields:
                return []

            exprs: list[Any] = [count("*").alias("_total_count")]
            specs: list[tuple] = []

            for index, field in enumerate(fields):
                column = col(field.name)
                dtype = field.dataType.simpleString()
                is_boolean = is_boolean_dtype(dtype)

                # Min/max are evaluated by the DB for all types (even if we ignore them later)
                min_expr = spark_min(column)
                max_expr = spark_max(column)

                null_alias = f"_c{index}_null"
                distinct_alias = f"_c{index}_distinct"
                min_alias = f"_c{index}_min"
                max_alias = f"_c{index}_max"

                exprs.extend(
                    [
                        count(when(column.isNull(), 1)).alias(null_alias),
                        countDistinct(column).alias(distinct_alias),
                        min_expr.alias(min_alias),
                        max_expr.alias(max_alias),
                    ]
                )

                specs.append(
                    (field, is_boolean, null_alias, distinct_alias, min_alias, max_alias)
                )

            stats = data.select(*exprs).first()
            total_rows = int(stats["_total_count"])

            rows: list[dict[str, Any]] = []

            for field, is_boolean, null_alias, distinct_alias, min_alias, max_alias in specs:
                dtype = field.dataType.simpleString()
                
                if is_boolean:
                    min_value = NOT_APPLICABLE
                    max_value = NOT_APPLICABLE
                elif is_string_dtype(dtype):
                    min_value = NOT_APPLICABLE
                    max_value = NOT_APPLICABLE
                else:
                    min_value = "" if stats[min_alias] is None else stats[min_alias]
                    max_value = "" if stats[max_alias] is None else stats[max_alias]

                rows.append(
                    {
                        "column_name": field.name,
                        "dtype": field.dataType.simpleString(),
                        "total_count": total_rows,
                        "null_count": int(stats[null_alias] or 0),
                        "distinct_count": int(stats[distinct_alias] or 0),
                        "min_value": min_value,
                        "max_value": max_value,
                    }
                )

            return rows
        except Exception:
            logger.exception(
                "Failed to profile DataFrame for profiler type '%s'",
                self.profiler_type,
            )
            raise


    def metadata(self) -> Mapping[str, Any]:
        """Return descriptive metadata about this profiler."""
        try:
            metadata = {
                "profiler_type": self.profiler_type,
            }
            logger.debug(
                "Generated metadata for profiler type '%s'",
                self.profiler_type,
            )
            return metadata
        except Exception:
            logger.exception(
                "Failed to generate metadata for profiler type '%s'",
                self.profiler_type,
            )
            raise
