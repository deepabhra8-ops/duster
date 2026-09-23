"""Helpers for resolving a column's effective dtype and formatting integer-like values consistently."""

from __future__ import annotations

from typing import Any

from pyspark.sql.types import DataType, DecimalType, DoubleType, FloatType
from utils.logger import get_logger


logger = get_logger(__name__)


NOT_APPLICABLE = "Not Applicable"


def is_string_dtype(
    dtype: str,
) -> bool:
    """Return whether a resolved dtype string is Spark's plain StringType.

    A lexicographic (alphabetical) min/max of free text - e.g. a SQL snippet or mapping-rule
    column - isn't a meaningful statistic, so profilers use this to substitute NOT_APPLICABLE
    for Min/Max on genuinely string-typed columns instead of displaying it.
    """
    return str(dtype).strip().lower() == "string"


def is_boolean_dtype(dtype: str) -> bool:
    """Return whether a resolved dtype string is boolean."""
    return str(dtype).strip().lower() == "boolean"


def is_date_like_dtype(dtype: str) -> bool:
    """Return whether a resolved dtype string is date or timestamp."""
    dtype_str = str(dtype).strip().lower()
    return dtype_str in ("date", "timestamp")

def resolve_effective_dtype(
    data_type: DataType,
) -> str:
    """Return a column's dtype as a short string (e.g. 'string', 'int', 'double', 'decimal(10,2)').

    Note: unlike the pandas version, this can't inspect actual values, so it no longer
    reclassifies a whole-number-valued float/double column as an integer dtype (pandas did
    this by scanning every value; doing the same in Spark would need an extra aggregate query
    per column). ``is_reclassified_integer`` below always returns False as a result - a known,
    accepted simplification, not a bug.
    """

    try:
        return data_type.simpleString()
    except Exception:
        logger.warning(
            "Unable to resolve effective dtype for column type '%s'; "
            "using its string representation",
            data_type,
            exc_info=True,
        )
        return str(data_type)


