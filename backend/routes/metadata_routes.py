from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import inspect

from services.connection_service import connection_service
from services.connectors import connector_registry
from services.metadata_engine_cache import get_cached_engine
from utils.logger import get_logger


logger = get_logger(__name__)

metadata_bp = APIRouter()


@metadata_bp.post("/api/metadata")
async def metadata(request: Request):
    """
    Return database metadata for the Configure page.

    Supported levels:
        schemas
        tables
        columns

    Optional:
        search

    Examples:

    Schemas:
    {
        "databaseType": "postgresql",
        "connectionDetails": {...},
        "level": "schemas",
        "search": "ana"
    }

    Tables:
    {
        "databaseType": "postgresql",
        "connectionDetails": {...},
        "level": "tables",
        "schema": "Analytics",
        "search": "cust"
    }

    Columns:
    {
        "databaseType": "postgresql",
        "connectionDetails": {...},
        "level": "columns",
        "schema": "Analytics",
        "table": "customer",
        "search": "customerid"
    }

    A connector whose DatabaseConnector.supports_sql_metadata_inspection() is False (no
    SQLAlchemy dialect to introspect - e.g. Salesforce) is routed to its own
    list_schemas()/list_tables()/list_columns() instead of the generic inspector below.
    """

    try:
        # ==========================================================
        # REQUEST BODY
        # ==========================================================

        body = await request.json()

        database_type = str(
            body.get("databaseType", "")
        ).strip().lower()

        connection_details = (
            body.get("connectionDetails") or {}
        )

        level = str(
            body.get("level", "schemas")
        ).strip().lower()

        schema = str(
            body.get("schema", "")
        ).strip()

        table = str(
            body.get("table", "")
        ).strip()

        search = str(
            body.get("search", "")
        ).strip()

        # ==========================================================
        # VALIDATION
        # ==========================================================

        if not database_type:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "databaseType is required",
                },
                status_code=400,
            )

        if not connection_details:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "connectionDetails is required",
                },
                status_code=400,
            )

        if level not in {
            "schemas",
            "tables",
            "columns",
        }:
            return JSONResponse(
                {
                    "ok": False,
                    "error": (
                        "level must be schemas, "
                        "tables, or columns"
                    ),
                },
                status_code=400,
            )

        connector = connector_registry.get(database_type)

        # A connector without generic SQL inspection (e.g. Salesforce) owns whatever notion
        # of "schema" makes sense for it - it may not need one selected first at all.
        uses_generic_sql_inspection = (
            connector is None
            or connector.supports_sql_metadata_inspection()
        )

        if (
            uses_generic_sql_inspection
            and level in {"tables", "columns"}
            and not schema
        ):
            return JSONResponse(
                {
                    "ok": False,
                    "error": (
                        "schema is required when "
                        f"level={level}"
                    ),
                },
                status_code=400,
            )

        if level == "columns" and not table:
            return JSONResponse(
                {
                    "ok": False,
                    "error": (
                        "table is required when "
                        "level=columns"
                    ),
                },
                status_code=400,
            )

        # Normalized search value.
        search_lower = search.lower()

        # ==========================================================
        # CONNECTOR-OWNED METADATA (no generic SQL inspection)
        # ==========================================================

        if connector is not None and not uses_generic_sql_inspection:

            logger.info(
                "Connector metadata request: type=%r | level=%r | "
                "schema=%r | table=%r | search=%r",
                database_type,
                level,
                schema,
                table,
                search,
            )

            if level == "schemas":
                items = connector.list_schemas(connection_details)
            elif level == "tables":
                items = connector.list_tables(connection_details, schema)
            else:
                items = connector.list_columns(connection_details, schema, table)

            if search_lower:
                items = [
                    item
                    for item in items
                    if search_lower in item.lower()
                ]

            return {
                "ok": True,
                "items": items,
            }

        # ==========================================================
        # DATABASE CONNECTION
        # ==========================================================

        connection_string = (
            connection_service.build_connection_string(
                database_type,
                connection_details,
            )
        )

        # Reuse a pooled engine per connection string instead of opening a brand-new
        # authenticated connection for every schema/table/column lookup - see
        # metadata_engine_cache.py for why this matters (repeated fresh logins can
        # trip a database's failed-login lockout under normal Configure-page usage).
        engine = get_cached_engine(connection_string)

        inspector = inspect(engine)

        # ==========================================================
        # SCHEMAS
        # ==========================================================

        if level == "schemas":

            logger.info(
                "Metadata request: schemas | search=%r",
                search,
            )

            items = inspector.get_schema_names()

            items = sorted(
                {
                    str(item).strip()
                    for item in items
                    if str(item).strip()
                }
            )

            if search_lower:
                items = [
                    item
                    for item in items
                    if search_lower in item.lower()
                ]

            logger.info(
                "Returning %d schemas",
                len(items),
            )

            return {
                "ok": True,
                "items": items,
            }

        # ==========================================================
        # TABLES
        # ==========================================================

        if level == "tables":

            logger.info(
                "Metadata request: tables | "
                "schema=%r | search=%r",
                schema,
                search,
            )

            items = inspector.get_table_names(
                schema=schema
            )

            items = sorted(
                {
                    str(item).strip()
                    for item in items
                    if str(item).strip()
                }
            )

            if search_lower:
                items = [
                    item
                    for item in items
                    if search_lower in item.lower()
                ]

            logger.info(
                "Returning %d tables for schema=%s",
                len(items),
                schema,
            )

            return {
                "ok": True,
                "items": items,
            }

        # ==========================================================
        # COLUMNS
        # ==========================================================

        if level == "columns":

            logger.info(
                "Metadata request: columns | "
                "schema=%r | table=%r | search=%r",
                schema,
                table,
                search,
            )

            columns = inspector.get_columns(
                table,
                schema=schema,
            )

            items = [
                str(column.get("name")).strip()
                for column in columns
                if column.get("name")
            ]

            items = sorted(items)

            if search_lower:
                items = [
                    item
                    for item in items
                    if search_lower in item.lower()
                ]

            logger.info(
                "Returning %d columns for %s.%s",
                len(items),
                schema,
                table,
            )

            return {
                "ok": True,
                "items": items,
            }

        # ==========================================================
        # FALLBACK
        # ==========================================================

        return JSONResponse(
            {
                "ok": False,
                "error": "Unsupported metadata level",
            },
            status_code=400,
        )

    except Exception as exc:

        logger.exception(
            "Metadata discovery failed"
        )

        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=400,
        )