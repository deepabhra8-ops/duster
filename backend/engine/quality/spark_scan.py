from __future__ import annotations

from typing import Any

from pyspark.sql import DataFrame
from pyspark.sql import functions as SF
from pyspark.sql.types import BooleanType

from engine.quality.evaluator import short_error
from engine.quality.families import family_of_spark
from engine.quality.planner import AggExpr
from engine.quality.sql_text import quote_ident, string_literal
from engine.quality.templates import BindingError


class SparkTableScan:
    def __init__(self, dataframe: DataFrame) -> None:
        self.df = dataframe

    def columns(self) -> list[tuple[str, str]]:
        # The live schema, not the metastore's view of it: stale metadata can't bind a
        # rule to a column that no longer exists or has changed type.
        return [(f.name, family_of_spark(f.dataType)) for f in self.df.schema.fields]

    def restrict(self, where: str) -> "SparkTableScan":
        return SparkTableScan(self.df.where(SF.expr(where)))

    def check_boolean(self, sql: str) -> None:
        # Spark analyses a new DataFrame eagerly, so this surfaces unknown columns, bad
        # syntax and type errors without running a job.
        try:
            data_type = self.df.select(SF.expr(sql).alias("__check")).schema["__check"].dataType
        except Exception as exc:
            raise BindingError(short_error(exc)) from exc

        if not isinstance(data_type, BooleanType):
            raise BindingError(f"Expression returns {data_type.simpleString()}, not BOOLEAN")

    def check_regex(self, pattern: str) -> None:
        # Spark compiles a literal regex only when it evaluates it, so a bad pattern
        # would otherwise fail the whole shared scan. This runs it once on a constant.
        try:
            self.df.sparkSession.sql(f"SELECT '' RLIKE {string_literal(pattern)} AS ok").collect()
        except Exception as exc:
            raise BindingError(f"Invalid regular expression: {short_error(exc)}") from exc

    def aggregate(self, exprs: list[AggExpr], sample: tuple[float, int] | None = None) -> dict[str, Any]:
        dataframe = self.df

        if sample is not None:
            fraction, seed = sample
            dataframe = dataframe.sample(fraction=fraction, seed=seed)

        row = dataframe.agg(*[SF.expr(expr.sql).alias(expr.alias) for expr in exprs]).first()
        return row.asDict() if row is not None else {}

    def key_coverage(
        self,
        column: str,
        row_filter: str | None,
        parent: "SparkTableScan",
        parent_column: str,
    ) -> tuple[int, int]:
        child = self.df

        if row_filter:
            child = child.where(SF.expr(f"coalesce(({row_filter}), false)"))

        keys = (
            child.select(SF.col(quote_ident(column)).alias("__key"))
            .where(SF.col("__key").isNotNull())
        )
        parent_keys = (
            parent.df.select(SF.col(quote_ident(parent_column)).alias("__key"))
            .where(SF.col("__key").isNotNull())
            .distinct()
            .withColumn("__hit", SF.lit(1))
        )

        row = (
            keys.join(parent_keys, on="__key", how="left")
            .agg(SF.count(SF.lit(1)).alias("total"), SF.count("__hit").alias("found"))
            .first()
        )
        return int(row["total"] or 0), int(row["found"] or 0)
