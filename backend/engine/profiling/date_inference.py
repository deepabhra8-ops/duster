from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, count, to_date, to_timestamp, trim, when

from utils.logger import get_logger


logger = get_logger(__name__)


DATE_FORMATS: tuple[str, ...] = (
    "yyyy-MM-dd",
    "yyyy/MM/dd",
    "MM/dd/yyyy",
    "dd/MM/yyyy",
    "dd-MMM-yyyy",
)

TIMESTAMP_FORMATS: tuple[str, ...] = (
    "yyyy-MM-dd HH:mm:ss",
    "yyyy-MM-dd'T'HH:mm:ss",
    "yyyy-MM-dd'T'HH:mm:ss.SSS",
    "yyyy-MM-dd'T'HH:mm:ssXXX",
)

ALL_FORMATS: tuple[str, ...] = DATE_FORMATS + TIMESTAMP_FORMATS


def _parser(fmt: str):
    return to_timestamp if "HH:mm" in fmt else to_date


def _string_columns(data: DataFrame) -> list[str]:
    return [
        field.name
        for field in data.schema.fields
        if field.dataType.simpleString() == "string"
    ]


def detect_formats(data: DataFrame) -> dict[str, str | None]:
    columns = _string_columns(data)

    if not columns:
        return {}

    aggregates = []

    for column in columns:
        value = col(column)
        non_blank = when(value.isNotNull() & (trim(value) != ""), 1)
        aggregates.append(count(non_blank).alias(f"{column}__total"))

        for index, fmt in enumerate(ALL_FORMATS):
            parsed = when(_parser(fmt)(value, fmt).isNotNull(), 1)
            aggregates.append(count(parsed).alias(f"{column}__fmt{index}"))

    row = data.agg(*aggregates).first()

    if row is None:
        return {}

    return {
        column: _choose_format(data, column, row)
        for column in columns
    }


def _choose_format(data: DataFrame, column: str, row) -> str | None:
    total = row[f"{column}__total"]

    if not total:
        return None

    candidates = [
        fmt
        for index, fmt in enumerate(ALL_FORMATS)
        if row[f"{column}__fmt{index}"] == total
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    return _resolve_ambiguity(data, column, candidates)


def _resolve_ambiguity(data: DataFrame, column: str, candidates: list[str]) -> str | None:
    first, *rest = candidates
    parse_first = _parser(first)(col(column), first)

    disagreements = data.filter(
        ~_all_agree(column, parse_first, rest)
    ).limit(1).count()

    if disagreements:
        logger.warning(
            "Column '%s' is ambiguous between %s - leaving it as text rather "
            "than guessing. Values will not be interpreted as dates.",
            column,
            " | ".join(candidates),
        )
        return None

    return first


def _all_agree(column: str, parse_first, rest: list[str]):
    condition = None

    for fmt in rest:
        same = parse_first.eqNullSafe(_parser(fmt)(col(column), fmt))
        condition = same if condition is None else (condition & same)

    return condition


def cast_date_columns(data: DataFrame) -> DataFrame:
    formats = detect_formats(data)

    for column, fmt in formats.items():
        if fmt is None:
            continue

        data = data.withColumn(column, _parser(fmt)(col(column), fmt))
        logger.info("Cast column '%s' using format '%s'", column, fmt)

    return data
