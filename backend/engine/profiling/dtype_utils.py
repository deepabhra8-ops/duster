from __future__ import annotations

from typing import Any

from pyspark.sql.types import DataType, DecimalType, DoubleType, FloatType
from utils.logger import get_logger


logger = get_logger(__name__)


NOT_APPLICABLE = "Not Applicable"


def is_string_dtype(
    dtype: str,
) -> bool:
    return str(dtype).strip().lower() == "string"


def is_boolean_dtype(dtype: str) -> bool:
    return str(dtype).strip().lower() == "boolean"


def is_date_like_dtype(dtype: str) -> bool:
    dtype_str = str(dtype).strip().lower()
    return dtype_str in ("date", "timestamp")

def resolve_effective_dtype(
    data_type: DataType,
) -> str:
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


