"""Generic SQLAlchemy-based writer: writes DataFrames to tables, creates schemas, and runs DDL/DML statements."""

from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from sqlalchemy import text
from sqlalchemy.engine import Engine

from engine.storage.jdbc_dialects import (
    build_bigquery_options,
    build_jdbc_target,
    dialect_of,
    is_bigquery,
    prepare_dataframe_for_jdbc_write,
)
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseWriter:
    """Writes DataFrames and runs statements against a database via a SQLAlchemy engine (or, for
    BigQuery, via Spark's dedicated BigQuery connector)."""

    def __init__(
        self,
        engine: Engine,
        db_config: Mapping[str, Any] | None = None,
    ) -> None:
        """Store the SQLAlchemy engine to write through, and (for BigQuery only) the raw
        service_account_json/project_id/dataset_id config the SQLAlchemy URL can't carry."""
        self.engine = engine
        self.db_config = db_config or {}

    _SAVE_MODES = {
        "fail": "error",
        "replace": "overwrite",
        "append": "append",
    }

    def write_table(
        self,
        data: DataFrame,
        table_name: str,
        schema: str | None = None,
        if_exists: str = "append",
        index: bool = False,
        chunksize: int = 10000,
        method: str | None = "multi",
    ) -> int:
        """Write a DataFrame to a database table via Spark JDBC, returning the row count written.

        ``index``/``chunksize``/``method`` are accepted for call-site compatibility with the
        pandas-era signature but no longer apply - Spark writes have no row index to carry,
        and partitioning/batching is controlled by the DataFrame's own partitions instead.
        Returning the count lets the caller (DatabaseStagingWriter) reuse it instead of
        counting `data` again itself.
        """
        _ = index, chunksize, method

        try:
            if data is None:
                raise ValueError(
                    "data cannot be None."
                )

            if not table_name or not str(table_name).strip():
                raise ValueError(
                    "table_name cannot be empty."
                )

            if if_exists not in self._SAVE_MODES:
                raise ValueError(
                    "if_exists must be one of: "
                    "fail, replace, append."
                )

            row_count = data.count()

            if is_bigquery(self.engine.url):
                self._write_bigquery(
                    data=data,
                    table_name=str(table_name).strip(),
                    mode=self._SAVE_MODES[if_exists],
                )
            else:
                jdbc_table = str(table_name).strip()

                if schema:
                    jdbc_table = f"{schema}.{jdbc_table}"

                target = build_jdbc_target(self.engine.url)

                properties = {
                    "driver": target.driver,
                    **target.properties,
                }

                # Redshift/Snowflake/Databricks have no built-in Spark JdbcDialect, so Spark's
                # generic type mapping applies and mis-maps some column types for them (e.g.
                # booleans -> "BIT", which none of the three support) - see jdbc_dialects.py.
                write_data, column_type_overrides = prepare_dataframe_for_jdbc_write(
                    data,
                    dialect_of(self.engine.url),
                )

                writer = write_data.write

                if column_type_overrides:
                    writer = writer.option(
                        "createTableColumnTypes",
                        column_type_overrides,
                    )

                writer.jdbc(
                    url=target.url,
                    table=jdbc_table,
                    mode=self._SAVE_MODES[if_exists],
                    properties=properties,
                )

            logger.info(
                "Wrote %s rows to database table '%s'",
                row_count,
                table_name,
            )
            return row_count
        except Exception:
            logger.exception("Failed to write database table '%s'", table_name)
            raise

    def _write_bigquery(
        self,
        data: DataFrame,
        table_name: str,
        mode: str,
    ) -> None:
        """Write a DataFrame to BigQuery via Spark's dedicated BigQuery connector."""
        dataset_id = str(self.db_config.get("dataset_id", "")).strip()

        if not dataset_id:
            raise ValueError(
                "BigQuery staging requires a dataset_id."
            )

        table_reference = f"{dataset_id}.{table_name}"

        options = build_bigquery_options(
            db_config=self.db_config,
            table_reference=table_reference,
        )

        (
            data.write.format("bigquery")
            .options(**options)
            .mode(mode)
            .save()
        )

    def create_schema(
        self,
        schema: str,
    ) -> None:
        """Create a database schema if the dialect supports it (PostgreSQL/Redshift/MSSQL)."""
        try:
            if not schema or not str(schema).strip():
                raise ValueError(
                    "schema cannot be empty."
                )

            dialect = self.engine.dialect.name.lower()

            if dialect in {
                "postgresql",
                "redshift",
            }:
                query = text(
                    f'CREATE SCHEMA IF NOT EXISTS '
                    f'"{self._escape_identifier(schema)}"'
                )

                with self.engine.begin() as connection:
                    connection.execute(query)

            elif dialect in {
                "mssql",
                "sqlserver",
            }:
                escaped_schema = self._escape_identifier(
                    schema
                )

                query = text(
                    "IF NOT EXISTS "
                    "(SELECT * FROM sys.schemas "
                    "WHERE name = :schema_name) "
                    f"EXEC('CREATE SCHEMA [{escaped_schema}]')"
                )

                with self.engine.begin() as connection:
                    connection.execute(
                        query,
                        {
                            "schema_name": schema,
                        },
                    )
            logger.info("Created database schema '%s'", schema)
        except Exception:
            logger.exception("Failed to create database schema '%s'", schema)
            raise

    def execute(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Run a statement within a transaction."""
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(query),
                    params or {},
                )
            logger.debug("Executed database statement")
        except Exception:
            logger.exception("Failed to execute database statement")
            raise

    def truncate_table(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> None:
        """Truncate a database table."""
        try:
            table_reference = self.build_table_reference(
                table_name=table_name,
                schema=schema,
            )

            query = text(
                f"TRUNCATE TABLE {table_reference}"
            )

            with self.engine.begin() as connection:
                connection.execute(query)
            logger.info("Truncated database table '%s'", table_name)
        except Exception:
            logger.exception("Failed to truncate database table '%s'", table_name)
            raise

    def table_exists(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> bool:
        """Return whether the given table exists."""
        try:
            from sqlalchemy import inspect

            inspector = inspect(self.engine)
            exists = inspector.has_table(
                table_name,
                schema=schema,
            )
            logger.debug("Checked database table '%s': exists=%s", table_name, exists)
            return exists
        except Exception:
            logger.exception("Failed to check database table '%s'", table_name)
            raise

    def build_table_reference(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> str:
        """Build a quoted schema.table reference."""
        table_name = str(table_name).strip()

        if not table_name:
            raise ValueError(
                "table_name cannot be empty."
            )

        table_identifier = self.quote_identifier(
            table_name
        )

        if schema:
            schema_identifier = self.quote_identifier(
                schema
            )

            return (
                f"{schema_identifier}."
                f"{table_identifier}"
            )

        return table_identifier

    @staticmethod
    def quote_identifier(
        identifier: str,
    ) -> str:
        """Quote a SQL identifier, escaping embedded quotes."""
        identifier = str(identifier).strip()

        if not identifier:
            raise ValueError(
                "Database identifier cannot be empty."
            )

        return (
            '"'
            + identifier.replace('"', '""')
            + '"'
        )

    @staticmethod
    def _escape_identifier(
        identifier: str,
    ) -> str:
        """Escape a schema name for safe interpolation into DDL."""
        return str(identifier).replace(
            "'",
            "''",
        )
