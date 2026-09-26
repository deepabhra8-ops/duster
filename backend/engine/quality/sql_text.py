from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any

from engine.quality.models import RuleValidationError


_SIMPLE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SELECT_KEYWORD = re.compile(r"\bselect\b", re.IGNORECASE)

MAX_FRAGMENT_LENGTH = 4000


def quote_ident(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def display_name(name: str) -> str:
    return name if _SIMPLE_IDENTIFIER.match(name) else quote_ident(name)


def display_fqn(*parts: str) -> str:
    return ".".join(display_name(part) for part in parts)


def string_literal(value: str) -> str:
    # Spark SQL unescapes backslash sequences inside string literals (with the default
    # spark.sql.parser.escapedStringLiterals=false), so every backslash is doubled and
    # quotes are backslash-escaped. A regex like ^\d+$ round-trips unchanged.
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def number_literal(value: Any) -> str:
    if isinstance(value, bool):
        raise RuleValidationError("Expected a number, got a boolean")

    if isinstance(value, int):
        return str(value)

    number = float(value)

    if not math.isfinite(number):
        raise RuleValidationError("Numbers must be finite")

    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))

    return repr(number)


def parse_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None

    text = str(value).strip()

    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        pass

    try:
        number = float(text)
    except ValueError:
        return None

    return number if math.isfinite(number) else None


def parse_temporal(value: Any) -> date | datetime | None:
    if not isinstance(value, str):
        return None

    text = value.strip()

    if _DATE_ONLY.match(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def temporal_literal(value: date | datetime) -> str:
    # The Spark session runs in UTC (see engine/core/spark_session.py), so naive
    # timestamps here mean UTC.
    if isinstance(value, datetime):
        return f"TIMESTAMP'{value.isoformat(sep=' ')}'"

    return f"DATE'{value.isoformat()}'"


def check_sql_fragment(text: str, field_name: str) -> str:
    """Accept a user-authored boolean expression (row filter, sql_row, run predicate).

    These run through Spark's expression parser, which cannot execute DDL/DML, but a
    scalar subquery could still read other tables, so subqueries and statement
    separators are refused outright.
    """
    fragment = str(text).strip()

    if not fragment:
        raise RuleValidationError(f"{field_name} cannot be empty")

    if len(fragment) > MAX_FRAGMENT_LENGTH:
        raise RuleValidationError(f"{field_name} must be at most {MAX_FRAGMENT_LENGTH} characters")

    if ";" in fragment:
        raise RuleValidationError(f"{field_name} must be a single expression (no ';')")

    if _SELECT_KEYWORD.search(fragment):
        raise RuleValidationError(f"{field_name} cannot contain a subquery (SELECT)")

    return fragment
