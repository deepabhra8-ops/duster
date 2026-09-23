"""Resolves and caches database reference tables (e.g. for DQ9 foreign-key checks) via a DatabaseReader."""

from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.reference_data.base_reference_provider import BaseReferenceProvider
from engine.storage.database_reader import DatabaseReader
from utils.logger import get_logger


logger = get_logger(__name__)


class TableReferenceProvider(BaseReferenceProvider):
    """Loads and caches reference tables from a database."""

    provider_type = "table"

    def __init__(
        self,
        context: ExecutionContext,
        database_reader: DatabaseReader | None = None,
    ) -> None:
        """Store the execution context and optional pre-built database reader."""
        super().__init__(context)
        self.database_reader = database_reader

    def get(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> DataFrame:
        """Return the reference table's data, loading and caching it on first use."""
        try:
            config = reference_config or {}

            cached = self.context.get_reference_data(
                reference_name,
            )

            if isinstance(cached, DataFrame):
                logger.debug("Loaded reference table '%s' from cache", reference_name)
                return cached

            table_name = str(
                config.get(
                    "table",
                    config.get(
                        "name",
                        reference_name,
                    ),
                ),
            ).strip()

            schema = str(
                config.get(
                    "schema",
                    "",
                )
            ).strip() or None

            columns = config.get("columns")

            if columns is not None:
                columns = list(columns)

            reader = self._get_reader(config)

            # Cached at the Spark level (not just in context.reference_data's Python dict)
            # so every later use of this reference table across the run - DQ9 checks on
            # multiple columns/tables, repeated get() calls - reuses this one materialized
            # result instead of re-issuing the JDBC query against the reference table again.
            dataframe = reader.read_table(
                table_name=table_name,
                schema=schema,
                columns=columns,
            ).cache()

            self.context.set_reference_data(
                reference_name,
                dataframe,
            )

            logger.info(
                "Loaded reference table '%s' (%s columns)",
                reference_name,
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to load reference table '%s'", reference_name)
            raise

    def exists(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the named reference table exists in the database."""
        try:
            config = reference_config or {}

            table_name = str(
                config.get(
                    "table",
                    config.get(
                        "name",
                        reference_name,
                    ),
                ),
            ).strip()

            if not table_name:
                return False

            schema = str(
                config.get(
                    "schema",
                    "",
                )
            ).strip() or None

            reader = self._get_reader(config)

            exists = reader.table_exists(
                table_name=table_name,
                schema=schema,
            )
            logger.debug("Checked reference table '%s': exists=%s", reference_name, exists)
            return exists
        except Exception:
            logger.debug(
                "Reference table '%s' does not exist or is unavailable",
                reference_name,
                exc_info=True,
            )
            return False

    def get_column(
        self,
        reference_name: str,
        column_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> DataFrame:
        """Return one column of a reference table, as a single-column DataFrame."""
        try:
            dataframe = self.get(
                reference_name=reference_name,
                reference_config=reference_config,
            )

            if column_name not in dataframe.columns:
                raise KeyError(
                    f"Column '{column_name}' does not exist "
                    f"in reference table '{reference_name}'."
                )

            return dataframe.select(column_name)
        except Exception:
            logger.exception(
                "Failed to load column '%s' from reference table '%s'",
                column_name,
                reference_name,
            )
            raise

    def clear_cache(
        self,
        reference_name: str | None = None,
    ) -> None:
        """Clear one cached reference table, or all of them when no name is given."""
        try:
            if reference_name is None:
                keys = list(
                    self.context.reference_data.keys()
                )

                for key in keys:
                    self.context.reference_data.pop(
                        key,
                        None,
                    )

                logger.info("Cleared %s cached reference entries", len(keys))
                return

            self.context.reference_data.pop(
                reference_name,
                None,
            )
            logger.info("Cleared cached reference table '%s'", reference_name)
        except Exception:
            logger.exception("Failed to clear reference table cache")
            raise

    def _get_reader(
        self,
        config: Mapping[str, Any],
    ) -> DatabaseReader:
        """Return the configured database reader, building one from a connection string if needed."""
        try:
            if self.database_reader is not None:
                return self.database_reader

            database_config = config.get(
                "db",
                {},
            )

            connection_string = database_config.get(
                "connection_string",
                config.get(
                    "connection_string",
                    "",
                ),
            )

            if not connection_string:
                raise ValueError(
                    "Reference table requires a database "
                    "connection_string."
                )

            from sqlalchemy import create_engine

            engine = create_engine(
                connection_string,
            )

            logger.debug("Created database reader for reference table")
            return DatabaseReader(
                engine=engine,
            )
        except Exception:
            logger.exception("Failed to create reference table database reader")
            raise
