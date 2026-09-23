"""Database implementation of BaseStagingWriter: writes curated rows to a staging schema via SQLAlchemy."""

from __future__ import annotations

from typing import Any, Mapping

from pyspark.sql import DataFrame
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from engine.core.execution_context import ExecutionContext
from engine.staging.base_staging_writer import BaseStagingWriter
from engine.staging.staging_writer_registry import register_staging_writer
from engine.storage.database_writer import DatabaseWriter
from utils.logger import get_logger


logger = get_logger(__name__)


@register_staging_writer
class DatabaseStagingWriter(BaseStagingWriter):
    """Writes curated rows into a database staging schema."""

    staging_type = "database"

    def write(
        self,
        table_name: str,
        data: DataFrame,
        staging_config: Mapping[str, Any],
    ) -> Any:
        """Create the staging schema if needed and write a table's curated rows into it."""
        engine = None

        try:
            db_config = staging_config.get(
                "db",
                {},
            )

            connection_string = str(
                db_config.get(
                    "connection_string",
                    "",
                )
            ).strip()

            if not connection_string:
                raise ValueError(
                    "Database staging requires a connection_string."
                )

            schema = str(
                db_config.get(
                    "schema",
                    "staging",
                )
            ).strip()

            if_exists = str(
                db_config.get(
                    "if_exists",
                    "append",
                )
            ).strip().lower()

            if if_exists not in {
                "append",
                "replace",
                "fail",
            }:
                raise ValueError(
                    "if_exists must be one of: "
                    "append, replace, fail."
                )

            engine = create_engine(
                connection_string
            )
            dialect = engine.dialect.name.lower()

            self._create_schema(
                engine=engine,
                schema=schema,
                dialect=dialect,
            )

            target_schema = (
                None
                if dialect in {
                    "sqlite",
                    "mysql",
                    "mariadb",
                }
                else schema
            )

            writer = DatabaseWriter(
                engine=engine,
                db_config=db_config,
            )

            # write_table() already counts `data` once (for its own log line) as it writes -
            # reuse that instead of counting a second time here.
            row_count = writer.write_table(
                data=data,
                table_name=str(table_name).lower(),
                schema=target_schema,
                if_exists=if_exists,
                index=False,
                chunksize=10000,
                method=(
                    None
                    if dialect == "sqlite"
                    else "multi"
                ),
            )

            result = {
                "table_name": str(table_name).lower(),
                "schema": target_schema,
                "rows_written": row_count,
                "if_exists": if_exists,
                "dialect": dialect,
            }
            logger.info(
                "Database staging completed for table '%s': %s rows written "
                "using '%s'",
                table_name,
                row_count,
                dialect,
            )
            return result

        except Exception:
            logger.exception(
                "Database staging failed for table '%s'",
                table_name,
            )
            raise

        finally:
            if engine is not None:
                engine.dispose()

    def supports(
        self,
        staging_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the staging config requests database staging."""
        try:
            staging_type = str(
                staging_config.get(
                    "type",
                    "database",
                )
            ).strip().lower()

            supported = staging_type == "database"
            logger.debug(
                "Database staging support check for type '%s': %s",
                staging_type,
                supported,
            )
            return supported
        except Exception:
            logger.exception(
                "Failed to check database staging support"
            )
            raise

    def validate_configuration(
        self,
        staging_config: Mapping[str, Any],
    ) -> None:
        """Validate that a database connection string is configured."""
        try:
            db_config = staging_config.get(
                "db",
                {},
            )

            connection_string = str(
                db_config.get(
                    "connection_string",
                    "",
                )
            ).strip()

            if not connection_string:
                raise ValueError(
                    "Database staging requires a connection_string."
                )

            logger.debug(
                "Database staging configuration validated"
            )
        except Exception:
            logger.exception(
                "Database staging configuration validation failed"
            )
            raise

    @staticmethod
    def _create_schema(
        engine: Engine,
        schema: str,
        dialect: str,
    ) -> None:
        """Create the staging schema if the dialect supports it; failures are logged, not raised."""
        if not schema:
            return

        try:
            with engine.begin() as connection:
                if dialect in {
                    "postgresql",
                    "redshift",
                }:
                    connection.execute(
                        text(
                            'CREATE SCHEMA IF NOT EXISTS '
                            f'"{DatabaseStagingWriter._escape_identifier(schema)}"'
                        )
                    )

                elif dialect in {
                    "mssql",
                    "sqlserver",
                }:
                    connection.execute(
                        text(
                            "IF NOT EXISTS "
                            "(SELECT * FROM sys.schemas "
                            "WHERE name = :schema_name) "
                            f"EXEC('CREATE SCHEMA "
                            f"[{DatabaseStagingWriter._escape_identifier(schema)}]')"
                        ),
                        {
                            "schema_name": schema,
                        },
                    )

        except Exception:
            logger.exception(
                "Failed to create database schema '%s' using dialect '%s'",
                schema,
                dialect,
            )
            pass

    @staticmethod
    def _escape_identifier(
        identifier: str,
    ) -> str:
        """Escape a schema name for safe interpolation into DDL."""
        return str(identifier).replace(
            '"',
            '""',
        ).replace(
            "]",
            "]]",
        )
