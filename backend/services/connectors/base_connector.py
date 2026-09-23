"""Defines the DatabaseConnector contract: building a connection string, validating required
fields, testing connectivity, and everything callers elsewhere (config_builder, metadata_routes)
need from a connector to avoid special-casing individual database types themselves.

Every method below beyond build_connection_string() has a default matching what every
JDBC/SQLAlchemy-backed connector already needs - override only what's actually different about
a new connector (e.g. SalesforceConnector, which has no SQLAlchemy dialect at all). Adding a
connector should never require editing config_builder.py, metadata_routes.py, or this file.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from core.config import DEFAULT_DATABASE_CONNECT_TIMEOUT
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseConnector(ABC):
    """Builds, validates, and tests a connection for one database type."""

    db_type: str = ""
    required_fields: tuple[str, ...] = ()

    # Connector-specific (regex, friendly message) pairs, checked before the generic patterns
    # in common/errors/friendly_errors.py - e.g. Salesforce's INVALID_LOGIN/INVALID_SECURITY_TOKEN.
    # Empty by default; describe_connection_error() falls through to its own generic patterns.
    error_patterns: tuple[tuple[re.Pattern[str], str], ...] = ()

    @abstractmethod
    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a SQLAlchemy-compatible connection string."""
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement "
            "build_connection_string()."
        )

    def validate(
        self,
        details: dict[str, Any],
    ) -> list[str]:
        """Return the required fields that are missing or blank."""

        return [
            field
            for field in self.required_fields
            if not str(details.get(field, "")).strip()
        ]

    def connect_args(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the SQLAlchemy connect_args used when testing the connection."""

        return {
            "connect_timeout": DEFAULT_DATABASE_CONNECT_TIMEOUT,
        }

    def test(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Test connectivity via SQLAlchemy; connectors that don't use SQLAlchemy override this."""

        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(
                self.build_connection_string(details),
                connect_args=self.connect_args(details),
            )

            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            logger.info(
                "Database connection test succeeded for type '%s'",
                self.db_type,
            )
            return {
                "ok": True,
                "message": f"{self.db_type.upper()} connected successfully ✅",
            }

        except Exception as exc:
            logger.warning(
                "Database connection test failed for type '%s': %s",
                self.db_type,
                exc,
            )
            return {
                "ok": False,
                "error": describe_connection_error(exc, self.error_patterns),
            }

    def accelerator_source_type(self) -> str:
        """Return the engine-side data source implementation this connector's data should be
        read through (the accelerator config's source.type). "database" for every JDBC/
        SQLAlchemy-backed connector (DatabaseDataSource); override when a connector needs its
        own data source (e.g. "salesforce" → SalesforceDataSource)."""
        return "database"

    def accelerator_credentials(self, details: dict[str, Any]) -> dict[str, Any]:
        """Return extra fields the engine-side data source needs directly, beyond
        connection_string (e.g. BigQuery's service_account_json, Salesforce's username/
        password/security_token/domain). Empty for connectors a connection_string fully
        describes."""
        return {}

    def supports_database_staging(self) -> bool:
        """Return whether curation-mode staging may write curated rows back into this
        database. False for connectors that aren't a valid staging target (e.g. Salesforce),
        which fall back to CSV staging instead."""
        return True

    def supports_sql_metadata_inspection(self) -> bool:
        """Return whether this connector's build_connection_string() output can be introspected
        via SQLAlchemy's generic `inspect()` for schema/table/column discovery. False only for
        connectors with no SQLAlchemy dialect at all, which must implement list_schemas()/
        list_tables()/list_columns() themselves instead."""
        return True

    def list_schemas(self, details: dict[str, Any]) -> list[str]:
        """Return this connection's available schemas. Only called when
        supports_sql_metadata_inspection() is False."""
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_schemas()."
        )

    def list_tables(self, details: dict[str, Any], schema: str) -> list[str]:
        """Return a schema's available tables. Only called when
        supports_sql_metadata_inspection() is False."""
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_tables()."
        )

    def list_columns(self, details: dict[str, Any], schema: str, table: str) -> list[str]:
        """Return a table's column names. Only called when
        supports_sql_metadata_inspection() is False."""
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_columns()."
        )
