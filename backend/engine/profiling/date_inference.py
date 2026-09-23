"""Detects date/timestamp formats in CSV string columns, and casts only when lossless.

This module previously destroyed data. It sampled the FIRST 100 rows, picked any
format that parsed more than 80% of that sample, and then applied it to the
ENTIRE column with to_date(). Spark's to_date() returns NULL for anything that
does not match, so every value outside the sample that used a different format -
and up to 19% of the sampled values themselves - was silently converted to NULL
before a single rule ran. In a data-quality tool that is the worst possible bug:
the anomalies the product exists to detect were being erased by the reader, and
what remained was then reported as a completeness failure with no trace of the
original value.

Two rules now govern casting:

1. A format is chosen from the WHOLE column, not a 100-row head sample, computed
   as one Spark aggregate across every candidate format and column at once.
2. A column is cast only when every non-blank value parses - a 100% rate. Below
   that, the column is left as a string and nothing is lost. Values that do not
   match then surface through the normal DQ2 date-format rule as findings, which
   is what the user asked the tool to tell them.

Ambiguity is refused rather than guessed. "01/02/2023" is valid under both
dd/MM/yyyy and MM/dd/yyyy; the old code silently preferred the US reading
because it was listed first. When two formats both parse the whole column but
disagree about what any value means, no format is chosen and the column stays a
string.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, count, to_date, to_timestamp, trim, when

from utils.logger import get_logger


logger = get_logger(__name__)


# Candidate formats, in Spark's pattern syntax. Order carries no authority - an
# ambiguous column is rejected rather than resolved by position (see module
# docstring). Epoch seconds are deliberately absent: they are indistinguishable
# from an ordinary integer id, and guessing is exactly the failure being fixed.
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
    """to_timestamp for formats carrying a time, to_date otherwise."""
    return to_timestamp if "HH:mm" in fmt else to_date


def _string_columns(data: DataFrame) -> list[str]:
    return [
        field.name
        for field in data.schema.fields
        if field.dataType.simpleString() == "string"
    ]


def detect_formats(data: DataFrame) -> dict[str, str | None]:
    """Return {column: format} for columns where exactly one format parses everything.

    A column maps to None when no format parses every value, or when more than
    one does and they disagree - both mean "do not cast this".

    Every column and candidate format is measured in a single Spark aggregate
    (one pass over the data) rather than a per-column sample pulled to the
    driver.
    """
    columns = _string_columns(data)

    if not columns:
        return {}

    aggregates = []

    for column in columns:
        value = col(column)
        # Blank-but-present strings are excluded from the denominator: they are
        # missing values, not malformed dates, and DQ1 is what reports them.
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
    """Pick the one format that parses the whole column, or None."""
    total = row[f"{column}__total"]

    if not total:
        # An all-null or all-blank column tells us nothing about its type.
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
    """Accept several fully-parsing formats only if they agree on every value.

    Formats can tie without being ambiguous - a column of "03/03/2023" parses
    identically under dd/MM and MM/dd. What matters is whether any row means
    something different depending on the format chosen. If one does, the column
    is genuinely ambiguous and must not be guessed.
    """
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
    """Predicate: every remaining candidate parses to the same instant as the first."""
    condition = None

    for fmt in rest:
        # eqNullSafe so two nulls count as agreement rather than as unknown.
        same = parse_first.eqNullSafe(_parser(fmt)(col(column), fmt))
        condition = same if condition is None else (condition & same)

    return condition


def cast_date_columns(data: DataFrame) -> DataFrame:
    """Cast string columns to date/timestamp, but only where no value would be lost.

    A column is cast only when every non-blank value parses under exactly one
    format. Anything less and the column is returned untouched as a string, so
    the reader can never null out a value - malformed dates stay visible and are
    reported by the date-format rule instead of disappearing here.
    """
    formats = detect_formats(data)

    for column, fmt in formats.items():
        if fmt is None:
            continue

        data = data.withColumn(column, _parser(fmt)(col(column), fmt))
        logger.info("Cast column '%s' using format '%s'", column, fmt)

    return data
