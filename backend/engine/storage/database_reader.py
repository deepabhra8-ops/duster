from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from sqlalchemy import text
from sqlalchemy.engine import Engine

from engine.core.spark_session import get_spark_session
from engine.storage.jdbc_dialects import apply_jdbc_target, build_jdbc_target
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseReader:
    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self.engine = engine

    def read_table(
        self,
        table_name: str,
        schema: str | None = None,
        columns: list[str] | None = None,
    ) -> DataFrame:
        try:
            query = self.build_select_query(
                table_name=table_name,
                schema=schema,
                columns=columns,
            )

            dataframe = self._read_jdbc(query.text, columns)
            logger.info(
                "Read database table '%s' (%s columns)",
                table_name,
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to read database table '%s'", table_name)
            raise

    def read_query(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
    ) -> DataFrame:
        try:
            if params:
                statement = text(query)

                with self.engine.connect() as connection:
                    result = connection.execute(statement, params)
                    rows = result.fetchall()
                    dataframe = get_spark_session().createDataFrame(
                        [tuple(row) for row in rows],
                        list(result.keys()),
                    )
            else:
                dataframe = self._read_jdbc(query)

            logger.info(
                "Read database query (%s columns)",
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to read database query")
            raise

    def read_chunks(
        self,
        table_name: str,
        schema: str | None = None,
        columns: list[str] | None = None,
        chunk_size: int = 0,
    ):
        yield self.read_table(
            table_name=table_name,
            schema=schema,
            columns=columns,
        )

    def read_query_chunks(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        chunk_size: int = 0,
    ):
        yield self.read_query(query=query, params=params)

    def table_exists(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> bool:
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

    def get_columns(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)

        columns = inspector.get_columns(
            table_name,
            schema=schema,
        )

        return [
            str(column["name"])
            for column in columns
        ]

    def get_column_metadata(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)

        return inspector.get_columns(
            table_name,
            schema=schema,
        )

    def get_row_count(
        self,
        table_name: str,
        schema: str | None = None,
    ) -> int:
        try:
            table_reference = self.build_table_reference(
                table_name=table_name,
                schema=schema,
            )

            query = text(
                f"SELECT COUNT(*) FROM {table_reference}"
            )

            with self.engine.connect() as connection:
                result = connection.execute(query)
                row_count = int(result.scalar() or 0)
            logger.debug("Database table '%s' contains %s rows", table_name, row_count)
            return row_count
        except Exception:
            logger.exception("Failed to count database table '%s'", table_name)
            raise

    def execute_scalar(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            statement = text(query)

            with self.engine.connect() as connection:
                result = connection.execute(
                    statement,
                    params or {},
                )

                value = result.scalar()
            logger.debug("Executed scalar database query")
            return value
        except Exception:
            logger.exception("Failed to execute scalar database query")
            raise

    def build_select_query(
        self,
        table_name: str,
        schema: str | None = None,
        columns: list[str] | None = None,
    ):
        try:
            table_reference = self.build_table_reference(
                table_name=table_name,
                schema=schema,
            )

            if columns:
                selected_columns = ", ".join(
                    self.quote_identifier(column)
                    for column in columns
                )
            else:
                selected_columns = "*"

            return text(
                f"SELECT {selected_columns} "
                f"FROM {table_reference}"
            )
        except Exception:
            logger.exception("Failed to build select query for table '%s'", table_name)
            raise

    @classmethod
    def build_table_reference(
        cls,
        table_name: str,
        schema: str | None = None,
    ) -> str:
        table_name = str(table_name).strip()

        if not table_name:
            raise ValueError(
                "table_name cannot be empty."
            )

        table_identifier = cls.quote_identifier(
            table_name
        )

        if schema:
            schema_identifier = cls.quote_identifier(
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
        try:
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
        except Exception:
            logger.exception("Failed to quote database identifier")
            raise

    def _read_jdbc(
        self,
        query: str,
        columns: list[str] | None = None,
    ) -> DataFrame:
        target = build_jdbc_target(self.engine.url)

        reader = get_spark_session().read.format("jdbc")
        reader = apply_jdbc_target(reader, target)
        reader = reader.option("dbtable", f"({query}) AS dq_query")

        dataframe = reader.load()
        return dataframe.select(*columns) if columns else dataframe
