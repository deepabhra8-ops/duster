"""Database implementation of BaseDataSource: reads tables via Spark JDBC (or the BigQuery connector), using the configured connection string."""

from __future__ import annotations

from typing import Any, Iterator, Mapping

from pyspark.sql import DataFrame
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from engine.core.spark_session import get_spark_session
from engine.data_sources.base_data_source import BaseDataSource
from engine.data_sources.source_registry import register_source
from engine.storage.jdbc_dialects import (
    apply_jdbc_target,
    build_bigquery_options,
    build_jdbc_target,
    is_bigquery,
)
from utils.logger import get_logger


logger = get_logger(__name__)


@register_source
class DatabaseDataSource(BaseDataSource):
    """Reads database tables as the data source, via Spark JDBC (or the BigQuery connector for BigQuery)."""

    source_type = "database"

    def __init__(
        self,
        config: Mapping[str, Any],
        context,
    ) -> None:
        """Store config/context and defer engine creation until first use."""
        super().__init__(
            config=config,
            context=context,
        )
        self._engine: Engine | None = None

    def read(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ) -> DataFrame:
        """Read a table into a DataFrame, optionally projecting columns."""
        try:
            connection_string = self._get_connection_string()

            if is_bigquery(connection_string):
                dataframe = self._read_bigquery(
                    table_config=table_config,
                    columns=columns,
                )
            else:
                dataframe = self._read_jdbc(
                    table_config=table_config,
                    columns=columns,
                )

            logger.info(
                "Read database source '%s' (%s columns)",
                str(table_config.get("name", "")).strip(),
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to read from database source")
            raise

    def read_chunks(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
        chunk_size: int = 0,
    ) -> Iterator[DataFrame]:
        """Read a table as a single Spark DataFrame (Spark partitions its own reads; there's no
        pandas-style chunked iteration to fall back to)."""
        yield self.read(
            table_config=table_config,
            columns=columns,
        )

    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the configured table exists in the database."""
        try:
            engine = self._get_engine()
            inspector = inspect(engine)
            table_name = str(table_config.get("name", "")).strip()
            schema = str(table_config.get("schema", "")).strip() or None

            if not table_name:
                return False

            exists = inspector.has_table(table_name, schema=schema)
            logger.debug("Checked database table '%s': exists=%s", table_name, exists)
            return exists
        except Exception:
            logger.exception("Failed to check database table existence")
            raise

    def get_columns(
        self,
        table_config: Mapping[str, Any],
    ) -> list[str]:
        """Return the table's column names via SQLAlchemy inspection."""
        engine = self._get_engine()

        inspector = inspect(engine)

        table_name = str(
            table_config.get("name", "")
        ).strip()

        schema = str(
            table_config.get("schema", "")
        ).strip() or None

        if not table_name:
            return []

        columns = inspector.get_columns(
            table_name,
            schema=schema,
        )

        return [
            str(column["name"])
            for column in columns
        ]

    def get_row_count(
        self,
        table_config: Mapping[str, Any],
    ) -> int:
        """Return the table's row count via a SELECT COUNT(*) query."""
        engine = self._get_engine()

        table_reference = self._build_table_reference(
            table_config
        )

        query = text(
            f"SELECT COUNT(*) FROM {table_reference}"
        )

        with engine.connect() as connection:
            result = connection.execute(query)
            return int(result.scalar() or 0)

    def supports_columns_projection(self) -> bool:
        """Database sources can read a subset of columns."""
        return True

    def supports_chunking(self) -> bool:
        """Database sources support chunked reads."""
        return False

    def profiler_dependencies(self) -> Mapping[str, Any]:
        """Expose the SQLAlchemy engine for profilers that need direct access."""
        return {
            "engine": self._get_engine(),
        }

    def validate_configuration(self) -> None:
        """Validate that a connection string is configured."""
        try:
            connection_string = self._get_connection_string()

            if not connection_string:
                raise ValueError(
                    "Database source requires a connection_string."
                )
            logger.debug("Database source configuration validated")
        except Exception:
            logger.exception("Database source configuration validation failed")
            raise

    def close(self) -> None:
        """Dispose the SQLAlchemy engine, if one was created."""
        try:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
                logger.debug("Closed database source engine")
        except Exception:
            logger.exception("Failed to close database source engine")
            raise

    def _get_engine(self) -> Engine:
        """Return the lazily created SQLAlchemy engine, creating it on first use."""
        try:
            if self._engine is None:
                connection_string = self._get_connection_string()

                if not connection_string:
                    raise ValueError(
                        "Database source requires a connection_string."
                    )

                self._engine = create_engine(
                    connection_string
                )
                logger.debug("Created database source engine")

            return self._engine
        except Exception:
            logger.exception("Failed to create database source engine")
            raise

        return self._engine

    def _get_db_config(self) -> Mapping[str, Any]:
        """Return the configured 'db' sub-config, if any."""
        return self.config.get("db", {})

    def _get_connection_string(self) -> str:
        """Return the configured connection string."""
        database_config = self._get_db_config()

        connection_string = database_config.get(
            "connection_string",
            "",
        )

        if not connection_string:
            connection_string = self.config.get(
                "connection_string",
                "",
            )

        return str(connection_string).strip()

    def _read_jdbc(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None,
    ) -> DataFrame:
        """Read a table via Spark JDBC, using the dialect resolved from the connection string."""
        query = self._build_select_query(
            table_config=table_config,
            columns=columns,
        )

        target = build_jdbc_target(
            make_url(self._get_connection_string())
        )

        reader = get_spark_session().read.format("jdbc")
        reader = apply_jdbc_target(reader, target)
        reader = reader.option("dbtable", f"({query.text}) AS dq_source")

        dataframe = reader.load()
        return dataframe.select(*columns) if columns else dataframe

    def _read_bigquery(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None,
    ) -> DataFrame:
        """Read a table via Spark's BigQuery connector."""
        db_config = self._get_db_config()

        dataset_id = str(db_config.get("dataset_id", "")).strip()
        table_name = str(table_config.get("name", "")).strip()

        if not dataset_id or not table_name:
            raise ValueError(
                "BigQuery source requires a dataset_id and a table 'name'."
            )

        table_reference = f"{dataset_id}.{table_name}"

        options = build_bigquery_options(
            db_config=db_config,
            table_reference=table_reference,
        )

        dataframe = (
            get_spark_session().read.format("bigquery")
            .options(**options)
            .load()
        )

        return dataframe.select(*columns) if columns else dataframe

    def _build_select_query(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ):
        """Build a SELECT query for a table, optionally projecting columns."""
        table_reference = self._build_table_reference(
            table_config
        )

        if columns:
            selected_columns = ", ".join(
                self._quote_identifier(column)
                for column in columns
            )
        else:
            selected_columns = "*"

        return text(
            f"SELECT {selected_columns} "
            f"FROM {table_reference}"
        )

    def _build_table_reference(
        self,
        table_config: Mapping[str, Any],
    ) -> str:
        """Build a quoted schema.table reference from the table config."""
        table_name = str(
            table_config.get("name", "")
        ).strip()

        schema = str(
            table_config.get("schema", "")
        ).strip()

        if not table_name:
            raise ValueError(
                "Database table configuration requires a 'name' value."
            )

        if schema:
            return (
                f"{self._quote_identifier(schema)}."
                f"{self._quote_identifier(table_name)}"
            )

        return self._quote_identifier(table_name)

    @staticmethod
    def _quote_identifier(
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
