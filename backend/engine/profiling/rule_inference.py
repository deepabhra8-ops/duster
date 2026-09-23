"""Infers likely DQ rule IDs for a column from its name and dtype, seeding the profile map's suggested rules."""

from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, count, countDistinct, max as spark_max, min as spark_min, when

from engine.profiling.dtype_utils import resolve_effective_dtype
from utils.logger import get_logger


logger = get_logger(__name__)


DATE_KEYWORDS = (
    "date",
    "time",
    "dt",
    "timestamp",
)

ID_KEYWORDS = (
    "id",
    "key",
    "code",
    "num",
    "number",
)

LOV_KEYWORDS = (
    "unit",
    "status",
    "group",
    "category",
    "country",
    "currency",
)


class RuleInference:
    """Infers a column's likely DQ rule IDs from its name and dtype."""

    def infer(
        self,
        data: DataFrame,
        column_name: str,
        column_profile: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Infer rule IDs for one column, building its profile if not supplied."""
        try:
            if column_name not in data.columns:
                logger.debug(
                    "Column '%s' not found; no rules inferred",
                    column_name,
                )
                return []

            profile = column_profile or self._build_profile(
                data,
                column_name,
            )

            dtype = str(
                profile.get(
                    "dtype",
                    resolve_effective_dtype(data.schema[column_name].dataType),
                )
            )

            inferred_rules = self._infer_rules(
                column_name=column_name,
                dtype=dtype,
            )

            logger.debug(
                "Inferred rules for column '%s': %s",
                column_name,
                inferred_rules,
            )
            return inferred_rules
        except Exception:
            logger.exception(
                "Failed to infer rules for column '%s'",
                column_name,
            )
            raise

    def infer_from_profile(
        self,
        column_name: str,
        dtype: str,
    ) -> list[str]:
        """Infer rule IDs for one column from already-computed profile stats - no DataFrame read needed."""
        try:
            inferred_rules = self._infer_rules(
                column_name=column_name,
                dtype=dtype,
            )
            logger.debug(
                "Inferred rules for column '%s': %s",
                column_name,
                inferred_rules,
            )
            return inferred_rules
        except Exception:
            logger.exception(
                "Failed to infer rules for column '%s'",
                column_name,
            )
            raise

    def infer_for_dataframe(
        self,
        data: DataFrame,
        profiles: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, list[str]]:
        """Infer rule IDs for every column in a DataFrame."""
        try:
            profiles = profiles or {}

            result = {
                column_name: self.infer(
                    data=data,
                    column_name=column_name,
                    column_profile=profiles.get(column_name),
                )
                for column_name in data.columns
            }
            logger.info(
                "Inferred rules for %s dataframe columns",
                len(result),
            )
            return result
        except Exception:
            logger.exception("Failed to infer rules for dataframe")
            raise

    @staticmethod
    def _infer_rules(
        column_name: str,
        dtype: str,
    ) -> list[str]:
        """Map a column's name keywords and dtype to a deduplicated list of rule IDs."""
        rules = ["DQ1"]

        col_lower = column_name.lower()
        dtype_lower = dtype.lower()

        if any(
            keyword in col_lower
            for keyword in DATE_KEYWORDS
        ):
            rules += ["DQ2", "DQ5"]

        if "float" in dtype_lower or "decimal" in dtype_lower or "double" in dtype_lower:
            rules += ["DQ4", "DQ5"]

        elif "int" in dtype_lower:
            rules += ["DQ5"]

        if "object" in dtype_lower or "str" in dtype_lower:
            rules += ["DQ3", "DQ6"]

            if any(
                keyword in col_lower
                for keyword in ID_KEYWORDS
            ):
                rules += ["DQ7", "DQ10"]

        if any(
            keyword in col_lower
            for keyword in LOV_KEYWORDS
        ):
            rules += ["DQ8"]

        return list(
            dict.fromkeys(rules)
        )

    def _build_profile(
        self,
        data: DataFrame,
        column_name: str,
    ) -> dict[str, Any]:
        """Build a lightweight column profile (dtype, counts, min/max) for rule inference, in one aggregate query."""
        try:
            column = col(column_name)

            stats = data.select(
                count("*").alias("total_count"),
                count(when(column.isNull(), 1)).alias("null_count"),
                countDistinct(column).alias("distinct_count"),
                spark_min(column).alias("min_value"),
                spark_max(column).alias("max_value"),
            ).first()

            return {
                "dtype": resolve_effective_dtype(
                    data.schema[column_name].dataType
                ),
                "total_count": int(stats["total_count"]),
                "null_count": int(stats["null_count"]),
                "distinct_count": int(stats["distinct_count"]),
                "min_value": stats["min_value"],
                "max_value": stats["max_value"],
            }
        except Exception:
            logger.exception(
                "Failed to build profile for column '%s'",
                column_name,
            )
            raise
