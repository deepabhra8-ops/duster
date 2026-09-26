from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from sqlalchemy import inspect

import engine.data_sources  # noqa: F401  (registers the database/salesforce/parquet sources)
from engine.core.execution_context import ExecutionContext
from engine.data_sources.source_registry import default_source_registry
from engine.quality.families import UNKNOWN, family_of_sqlalchemy
from engine.quality.models import TableRef
from engine.quality.scope import KIND_TABLE, KIND_VIEW
from engine.quality.spark_scan import SparkTableScan
from services.connection_service import connection_service
from services.connectors import connector_registry
from services.metadata_engine_cache import get_cached_engine
from services.saved_connection_service import saved_connection_service
from utils.logger import get_logger


logger = get_logger(__name__)


class UnknownCatalogError(KeyError):
    pass


class ConnectionCatalog:
    """Maps the rule model's catalog → schema → table → column hierarchy onto DUSTER's
    saved connections: every saved connection is a catalog, named by the connection's
    name, and its schemas, tables and columns come from the source database's own
    metadata. A Databricks connection is already pinned to one Unity Catalog catalog,
    and a MySQL connection's "schemas" are its databases."""

    def __init__(self) -> None:
        self._by_name: dict[str, dict[str, Any]] | None = None
        self._decrypted: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _connections(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._by_name is None:
                self._by_name = {row["name"]: row for row in saved_connection_service.list_all()}

            return self._by_name

    def connection(self, catalog: str) -> dict[str, Any]:
        summary = self._connections().get(catalog)

        if summary is None:
            raise UnknownCatalogError(f"No saved connection named '{catalog}'")

        with self._lock:
            cached = self._decrypted.get(catalog)

        if cached is not None:
            return cached

        decrypted = saved_connection_service.get_decrypted_for_run(summary["id"])

        if decrypted is None:
            raise UnknownCatalogError(f"Saved connection '{catalog}' no longer exists")

        with self._lock:
            self._decrypted[catalog] = decrypted

        return decrypted

    def _sql_inspector(self, catalog: str):
        decrypted = self.connection(catalog)
        connector = connector_registry.get(decrypted["db_type"])

        if connector is not None and not connector.supports_sql_metadata_inspection():
            return None, connector, decrypted["connection_details"]

        connection_string = connection_service.build_connection_string(
            decrypted["db_type"],
            decrypted["connection_details"],
        )
        return inspect(get_cached_engine(connection_string)), connector, decrypted["connection_details"]

    def list_catalogs(self) -> list[str]:
        return list(self._connections())

    def list_schemas(self, catalog: str) -> list[str]:
        inspector, connector, details = self._sql_inspector(catalog)

        if inspector is None:
            return list(connector.list_schemas(details))

        return [str(name) for name in inspector.get_schema_names()]

    def list_tables(self, catalog: str, schema: str) -> list[tuple[str, str]]:
        inspector, connector, details = self._sql_inspector(catalog)

        if inspector is None:
            return [(str(name), KIND_TABLE) for name in connector.list_tables(details, schema)]

        tables = [(str(name), KIND_TABLE) for name in inspector.get_table_names(schema=schema)]

        try:
            tables += [(str(name), KIND_VIEW) for name in inspector.get_view_names(schema=schema)]
        except NotImplementedError:
            logger.debug("View listing unsupported for catalog '%s'", catalog)

        return tables

    def list_columns(self, catalog: str, schema: str, table: str) -> list[tuple[str, str]]:
        inspector, connector, details = self._sql_inspector(catalog)

        if inspector is None:
            return [(str(name), UNKNOWN) for name in connector.list_columns(details, schema, table)]

        return [
            (str(column["name"]), family_of_sqlalchemy(column.get("type")))
            for column in inspector.get_columns(table, schema=schema)
        ]


class ConnectionTableSource:
    """Opens a resolved table as a Spark DataFrame through the same data-source layer the
    validator uses (JDBC, BigQuery, Salesforce). Spark prunes the JDBC read to the
    columns the checks reference and pushes simple run predicates down to the source."""

    def __init__(self, catalog: ConnectionCatalog) -> None:
        self.catalog = catalog
        self._run_timestamp = datetime.utcnow().isoformat(timespec="seconds")

    def open(self, table: TableRef) -> SparkTableScan:
        decrypted = self.catalog.connection(table.catalog)
        db_type = str(decrypted["db_type"]).strip().lower()
        details = decrypted["connection_details"]
        connector = connector_registry.get(db_type)

        if connector is None:
            raise ValueError(f"Unsupported database type '{db_type}' for '{table.catalog}'")

        db_config = {
            "connection_string": connector.build_connection_string(details),
            **connector.accelerator_credentials(details),
        }

        if db_type == "bigquery":
            db_config["dataset_id"] = table.schema

        source = default_source_registry.get(
            source_type=connector.accelerator_source_type(),
            config={"db": db_config},
            context=ExecutionContext(project_name="data-quality", run_timestamp=self._run_timestamp),
        )

        dataframe = source.read({"name": table.table, "schema": table.schema})
        return SparkTableScan(dataframe)
