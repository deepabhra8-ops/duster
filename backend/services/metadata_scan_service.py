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
    def list_schemas(
        self,
        database_type: str,
        connection_details: dict[str, Any],
    ) -> list[str]:
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
        if not schema:
            raise ValueError("schema is required")

        connector = self._connector_for(database_type, connection_details)

        if connector is not None:
            return self._clean(connector.list_tables(connection_details, schema))[
                :METADATA_SCAN_MAX_TABLES_PER_SCHEMA
            ]

        inspector = self._inspector(database_type, connection_details)

        names = list(inspector.get_table_names(schema=schema))

        try:
            names.extend(inspector.get_view_names(schema=schema))
        except Exception:
            logger.debug("View listing unsupported for '%s'", database_type)

        return self._clean(names)[:METADATA_SCAN_MAX_TABLES_PER_SCHEMA]

    def list_columns(
        self,
        database_type: str,
        connection_details: dict[str, Any],
        schema: str,
        table: str,
    ) -> list[str]:
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
        return sorted({str(name).strip() for name in names if str(name or "").strip()})


metadata_scan_service = MetadataScanService()
