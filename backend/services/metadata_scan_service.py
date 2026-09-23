"""Per-level database catalog lookups: schemas, then a schema's tables, then a
table's columns.

Deliberately *not* a whole-catalog walk. Enumerating every schema -> table ->
column up front is slow enough on a large database to stall the request that
triggers it, produces a payload big enough to be awkward to store, and is stale
as soon as anyone changes the source. Each level is fetched only when the user
actually opens it, so the cost scales with what they look at rather than with the
size of the database.

Only the schema name list is ever persisted (on the connection), because it is
small and makes the first dropdown instant. Tables and columns are always live.

Runs in the web container: pure SQLAlchemy inspection, no Spark.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect

from core.config import (
    METADATA_SCAN_MAX_SCHEMAS,
    METADATA_SCAN_MAX_TABLES_PER_SCHEMA,
)
from services.connection_service import connection_service
from services.connectors import connector_registry
from services.metadata_engine_cache import get_cached_engine
from utils.logger import get_logger


logger = get_logger(__name__)


class MetadataScanService:
    """Resolves one catalog level at a time for a database connection."""

    def list_schemas(
        self,
        database_type: str,
        connection_details: dict[str, Any],
    ) -> list[str]:
        """Return the connection's schema names.

        This is the only level fetched when a connection is saved - it is a single
        catalog query, so it stays fast regardless of how many tables exist.
        """
        connector = self._connector_for(database_type, connection_details)

        if connector is not None:
            return self._clean(connector.list_schemas(connection_details))[
                :METADATA_SCAN_MAX_SCHEMAS
            ]

        inspector = self._inspector(database_type, connection_details)
        return self._clean(inspector.get_schema_names())[:METADATA_SCAN_MAX_SCHEMAS]

    def list_tables(
        self,
        database_type: str,
        connection_details: dict[str, Any],
        schema: str,
    ) -> list[str]:
        """Return one schema's table names."""
        if not schema:
            raise ValueError("schema is required")

        connector = self._connector_for(database_type, connection_details)

        if connector is not None:
            return self._clean(connector.list_tables(connection_details, schema))[
                :METADATA_SCAN_MAX_TABLES_PER_SCHEMA
            ]

        inspector = self._inspector(database_type, connection_details)

        # Views are legitimate profiling targets, so include them alongside tables.
        names = list(inspector.get_table_names(schema=schema))

        try:
            names.extend(inspector.get_view_names(schema=schema))
        except Exception:
            # Not every dialect implements view reflection; tables alone are fine.
            logger.debug("View listing unsupported for '%s'", database_type)

        return self._clean(names)[:METADATA_SCAN_MAX_TABLES_PER_SCHEMA]

    def list_columns(
        self,
        database_type: str,
        connection_details: dict[str, Any],
        schema: str,
        table: str,
    ) -> list[str]:
        """Return one table's column names."""
        if not schema:
            raise ValueError("schema is required")

        if not table:
            raise ValueError("table is required")

        connector = self._connector_for(database_type, connection_details)

        if connector is not None:
            return self._clean(
                connector.list_columns(connection_details, schema, table)
            )

        inspector = self._inspector(database_type, connection_details)

        return self._clean(
            column.get("name")
            for column in inspector.get_columns(table, schema=schema)
        )

    def _connector_for(
        self,
        database_type: str,
        connection_details: dict[str, Any],
    ):
        """Return the connector to use directly, or None to use SQLAlchemy inspection.

        Only connectors with no SQLAlchemy dialect at all (e.g. Salesforce) resolve
        their own levels; everything else goes through the generic inspector.
        """
        database_type = self._require(database_type, "databaseType")

        if not connection_details:
            raise ValueError("connectionDetails is required")

        connector = connector_registry.get(database_type)

        if connector is None or connector.supports_sql_metadata_inspection():
            return None

        return connector

    def _inspector(
        self,
        database_type: str,
        connection_details: dict[str, Any],
    ):
        """Return a SQLAlchemy inspector on the shared, pooled engine.

        Uses the engine cache rather than building one per call: these lookups fire
        on every dropdown the user opens, and a fresh engine each time means a fresh
        authentication handshake - enough repeated logins to trip a database's
        failed-login lockout. The cache owns the engine, so nothing here disposes it.
        """
        connection_string = connection_service.build_connection_string(
            self._require(database_type, "databaseType"),
            connection_details,
        )

        return inspect(get_cached_engine(connection_string))

    @staticmethod
    def _require(value: str, field: str) -> str:
        normalized = str(value or "").strip().lower()

        if not normalized:
            raise ValueError(f"{field} is required")

        return normalized

    @staticmethod
    def _clean(names) -> list[str]:
        """Return sorted, de-duplicated, non-empty names."""
        return sorted({str(name).strip() for name in names if str(name or "").strip()})


metadata_scan_service = MetadataScanService()
