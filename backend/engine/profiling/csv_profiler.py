from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, count, countDistinct, max as spark_max, min as spark_min, when

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import (
    ProfileColumnResult,
    TableProfileResult,
)
from engine.profiling.base_profiler import BaseProfiler
from engine.profiling.dtype_utils import (
    NOT_APPLICABLE,
    is_boolean_dtype,
    is_string_dtype,
    resolve_effective_dtype,
)
from engine.profiling.profiler_registry import register_profiler
from utils.logger import get_logger


logger = get_logger(__name__)


@register_profiler
class CsvProfiler(BaseProfiler):
    profiler_type = "csv"

    def profile(
        self,
        data: DataFrame,
        table_config: Mapping[str, Any],
    ) -> TableProfileResult:
        try:
            table_name = str(
                table_config.get(
                    "name",
                    table_config.get(
                        "table",
                        "",
                    ),
                ),
            ).strip()

            if not table_name:
                table_name = str(
                    table_config.get(
                        "file",
                        "table",
                    )
                ).strip()

            columns = self._profile_columns(data)

            result = TableProfileResult(
                table_name=table_name,
                columns=columns,
            )
            logger.info(
                "Profiled CSV table '%s' with %s columns and %s rows",
                table_name,
                len(columns),
                columns[0].total_count if columns else 0,
            )
            return result
        except Exception:
            logger.exception("Failed to profile CSV table")
            raise

    def supports(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        logger.debug("CSV profiler supports the supplied table configuration")
        return True

    def _profile_columns(
        self,
        data: DataFrame,
    ) -> list[ProfileColumnResult]:
        try:
            column_names = data.columns

            if not column_names:
                return []

            exprs: list[Any] = [count("*").alias("_total_count")]
            specs: list[tuple] = []

            for index, column_name in enumerate(column_names):
                column = col(column_name)

                null_alias = f"_c{index}_null"
                distinct_alias = f"_c{index}_distinct"
                min_alias = f"_c{index}_min"
                max_alias = f"_c{index}_max"

                exprs.extend(
                    [
                        count(when(column.isNull(), 1)).alias(null_alias),
                        countDistinct(column).alias(distinct_alias),
                        spark_min(column).alias(min_alias),
                        spark_max(column).alias(max_alias),
                    ]
                )

                specs.append(
                    (column_name, null_alias, distinct_alias, min_alias, max_alias)
                )

            stats = data.select(*exprs).first()
            total_count = int(stats["_total_count"])

            columns: list[ProfileColumnResult] = []

            for column_name, null_alias, distinct_alias, min_alias, max_alias in specs:
                data_type = data.schema[column_name].dataType
                dtype = resolve_effective_dtype(data_type)

                if is_string_dtype(dtype) or is_boolean_dtype(dtype):
                    min_value = NOT_APPLICABLE
                    max_value = NOT_APPLICABLE
                else:
                    min_value = self._safe_value(stats[min_alias])
                    max_value = self._safe_value(stats[max_alias])

                columns.append(
                    ProfileColumnResult(
                        column_name=column_name,
                        dtype=dtype,
                        total_count=total_count,
                        null_count=int(stats[null_alias]),
                        distinct_count=int(stats[distinct_alias]),
                        min_value=min_value,
                        max_value=max_value,
                    )
                )

            return columns
        except Exception:
            logger.exception(
                "Failed to profile CSV DataFrame"
            )
            raise

    @staticmethod
    def _safe_value(
        value: Any,
    ) -> Any:
        if value is None:
            return ""

        return value
