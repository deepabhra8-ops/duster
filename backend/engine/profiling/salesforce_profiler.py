from __future__ import annotations

from typing import Any, Callable, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.result_models import (
    ProfileColumnResult,
    TableProfileResult,
)
from engine.profiling.base_profiler import BaseProfiler
from engine.profiling.profiler_registry import register_profiler
from engine.profiling.salesforce_type_mapping import map_salesforce_type
from utils.logger import get_logger


logger = get_logger(__name__)


@register_profiler
class SalesforceProfiler(BaseProfiler):
    profiler_type = "salesforce"

    def __init__(
        self,
        context: ExecutionContext,
        field_type_resolver: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        super().__init__(context)
        self.field_type_resolver = field_type_resolver

    def profile(
        self,
        data: DataFrame,
        table_config: Mapping[str, Any],
    ) -> TableProfileResult:
        try:
            object_name = str(
                table_config.get("name", "")
            ).strip()

            if not object_name:
                raise ValueError(
                    "Salesforce object configuration requires a 'name' value."
                )

            rows = self._profile_dataframe(data)

            self._apply_salesforce_type_labels(
                rows=rows,
                object_name=object_name,
            )

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
                table_name=object_name,
                columns=columns,
            )
            logger.info(
                "Profiled Salesforce object '%s' with %s columns",
                object_name,
                len(columns),
            )
            return result
        except Exception:
            logger.exception("Failed to profile Salesforce object")
            raise

    def _apply_salesforce_type_labels(
        self,
        rows: list[dict[str, Any]],
        object_name: str,
    ) -> None:
        if self.field_type_resolver is None:
            return

        try:
            sf_types = self.field_type_resolver(object_name)
        except Exception:
            logger.warning(
                "Failed to resolve Salesforce field types for '%s'; "
                "profile map will show Spark-derived dtypes instead",
                object_name,
                exc_info=True,
            )
            return

        for row in rows:
            sf_type = sf_types.get(row["column_name"], "")
            row["dtype"] = map_salesforce_type(sf_type)

