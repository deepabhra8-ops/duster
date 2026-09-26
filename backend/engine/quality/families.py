from __future__ import annotations

from typing import Any, Iterable


NUMERIC = "numeric"
STRING = "string"
TEMPORAL = "temporal"
BOOLEAN = "boolean"
BINARY = "binary"
COMPLEX = "complex"
OTHER = "other"
# Dry runs read column types from the source's metadata, and connectors without SQL
# inspection (Salesforce) only report names. Unknown columns bind provisionally; the
# live Spark schema re-checks them when the run starts.
UNKNOWN = "unknown"
ANY = "any"

FAMILIES = (NUMERIC, STRING, TEMPORAL, BOOLEAN, BINARY, COMPLEX)
DECLARABLE = FAMILIES + (ANY,)


def fits(allowed: Iterable[str], family: str) -> bool:
    allowed = set(allowed)
    return ANY in allowed or family == UNKNOWN or family in allowed


def describe(allowed: Iterable[str]) -> str:
    return "[" + ", ".join(sorted(allowed)) + "]"


def family_of_spark(data_type: Any) -> str:
    from pyspark.sql import types as T

    groups = (
        (NUMERIC, (T.ByteType, T.ShortType, T.IntegerType, T.LongType, T.FloatType, T.DoubleType, T.DecimalType)),
        (STRING, (T.StringType, T.CharType, T.VarcharType)),
        (TEMPORAL, (T.DateType, T.TimestampType, T.TimestampNTZType)),
        (BOOLEAN, (T.BooleanType,)),
        (BINARY, (T.BinaryType,)),
        (COMPLEX, (T.ArrayType, T.MapType, T.StructType)),
    )

    for family, classes in groups:
        if isinstance(data_type, classes):
            return family

    return OTHER


def family_of_sqlalchemy(column_type: Any) -> str:
    from sqlalchemy import types as S

    if column_type is None or isinstance(column_type, S.NullType):
        return UNKNOWN

    groups = (
        (BOOLEAN, (S.Boolean,)),
        (NUMERIC, (S.Integer, S.Numeric, S.Float)),
        (TEMPORAL, (S.Date, S.DateTime, S.Time)),
        (STRING, (S.String, S.Enum)),
        (BINARY, (S._Binary,)),
        (COMPLEX, (S.ARRAY, S.JSON)),
    )

    for family, classes in groups:
        if isinstance(column_type, classes):
            return family

    return UNKNOWN
