"""HTTP endpoints for testing database connections and managing saved connections.

Saved connections are shared but owner-managed: any authenticated user may list
and use one, but only its creator (or an admin) may edit, delete, or reveal its
credentials - see SavedConnectionService, which enforces that.

The whole router is registered with Depends(require_auth) in create_app(), so
every route here is authenticated; routes needing the *identity* (for ownership)
declare the dependency again to receive the username.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from routes.auth_routes import require_auth
from services.connection_service import connection_service
from services.saved_connection_service import (
    ConnectionPermissionError,
    saved_connection_service,
)
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger


logger = get_logger(__name__)


connection_bp = APIRouter()


def _error(message: str, status_code: int) -> JSONResponse:
    """Build the error envelope the frontend's axios wrapper expects.

    api.js reads err.response.data.error, so every failure must carry a
    top-level "error" string or the UI shows a bare status code.
    """
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@connection_bp.post("/api/test-connection")
async def test_connection(request: Request):
    """Test a database connection using the supplied connection details."""
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        database_type = body.get(
            "databaseType",
            "",
        )

        connection_details = body.get(
            "connectionDetails",
            {},
        )

        if not database_type and body.get("connection_string"):
            result = connection_service.test_connection_string(
                body["connection_string"]
            )

            if result.get("ok"):
                logger.info("Legacy database connection test succeeded")
                return result

            logger.warning("Legacy database connection test failed")
            return JSONResponse(result, status_code=400)

        if not database_type:
            logger.warning("Database connection test missing database type")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "databaseType is required",
                },
                status_code=400,
            )

        result = connection_service.test_connection(
            db_type=database_type,
            details=connection_details,
        )

        if result.get("ok"):
            logger.info(
                "Database connection test succeeded for type '%s'",
                database_type,
            )
            return result

        logger.warning(
            "Database connection test failed for type '%s'",
            database_type,
        )
        return JSONResponse(result, status_code=400)
    except Exception:
        logger.exception("Unexpected database connection route failure")
        raise


# =====================================================================
# SAVED CONNECTIONS
# =====================================================================


@connection_bp.get("/api/connections")
def list_connections(request: Request):
    """List saved connections. Never returns credentials.

    Two callers, two response shapes, told apart by whether `page` is present:

    - The job wizard's connection picker (useSavedConnections.js) calls this
      with no query params at all, and needs every connection back to search/
      select from - so that shape is preserved exactly as before.
    - The Connections manager page calls it with `page`/`pageSize` (+ optional
      `search`/`dbType`/`sortOrder`), and gets one page back, filtered and
      sorted in SQL - see SavedConnectionService.list_page.
    """
    try:
        page_param = request.query_params.get("page")

        if page_param is None:
            return {"ok": True, "data": saved_connection_service.list_all()}

        try:
            page = int(page_param)
            page_size = int(request.query_params.get("pageSize", 10))
        except ValueError:
            return _error("page and pageSize must be integers", 400)

        if page < 1 or page_size < 1:
            return _error("page and pageSize must be greater than 0", 400)

        search = request.query_params.get("search", "").strip()
        db_type = request.query_params.get("dbType", "").strip()
        sort_order = request.query_params.get("sortOrder", "desc")

        result = saved_connection_service.list_page(
            search=search,
            db_type=db_type,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        return {"ok": True, **result}
    except Exception:
        logger.exception("Failed to list saved connections")
        return _error("Failed to load saved connections", 500)


@connection_bp.post("/api/connections")
async def create_connection(
    request: Request,
    username: str = Depends(require_auth),
):
    """Create a saved connection owned by the current user."""
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        created = saved_connection_service.create(
            name=body.get("name", ""),
            db_type=body.get("databaseType", ""),
            connection_details=body.get("connectionDetails", {}),
            created_by=username,
            description=body.get("description", ""),
        )

        # No catalog work here on purpose. Saving a connection used to run a
        # schema query first, which made the user wait on "fetching schemas" for
        # something they had not asked for - they are saving a connection, not
        # building a job - and the result went stale as soon as the source
        # changed. Schemas are read live when a connection is actually picked,
        # the same way tables and columns already were. See migration 007.
        return {"ok": True, "data": created}
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to create saved connection")
        return _error("Failed to save the connection", 500)


@connection_bp.patch("/api/connections/{connection_id}")
async def update_connection(
    connection_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    """Update a saved connection. Owner (or admin) only."""
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        updated = saved_connection_service.update(
            connection_id=connection_id,
            name=body.get("name", ""),
            db_type=body.get("databaseType", ""),
            connection_details=body.get("connectionDetails", {}),
            username=username,
            description=body.get("description", ""),
        )

        if updated is None:
            return _error("Connection not found", 404)

        return {"ok": True, "data": updated}
    except ConnectionPermissionError as exc:
        return _error(str(exc), 403)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to update saved connection '%s'", connection_id)
        return _error("Failed to update the connection", 500)


@connection_bp.delete("/api/connections/{connection_id}")
def delete_connection(
    connection_id: str,
    username: str = Depends(require_auth),
):
    """Delete a saved connection. Owner (or admin) only.

    Jobs that referenced it keep their history - the FK is ON DELETE SET NULL.
    """
    try:
        if not saved_connection_service.delete(connection_id, username):
            return _error("Connection not found", 404)

        return {"ok": True}
    except ConnectionPermissionError as exc:
        return _error(str(exc), 403)
    except Exception:
        logger.exception("Failed to delete saved connection '%s'", connection_id)
        return _error("Failed to delete the connection", 500)


@connection_bp.get("/api/connections/{connection_id}/reveal")
def reveal_connection(
    connection_id: str,
    username: str = Depends(require_auth),
):
    """Return a saved connection's decrypted credentials, so its owner can pre-fill
    the edit form. Owner (or admin) only - this is the one path by which stored
    credentials leave the server, and every call is logged.
    """
    try:
        revealed = saved_connection_service.reveal(connection_id, username)

        if revealed is None:
            return _error("Connection not found", 404)

        return {
            "ok": True,
            "data": {"connection_details": revealed["connection_details"]},
        }
    except ConnectionPermissionError as exc:
        return _error(str(exc), 403)
    except ValueError as exc:
        # Raised by crypto.decrypt_json when the encryption key has been rotated.
        return _error(str(exc), 500)
    except Exception:
        logger.exception("Failed to reveal saved connection '%s'", connection_id)
        return _error("Failed to read the connection", 500)


# =====================================================================
# CATALOG - one level at a time
# =====================================================================
#
# None of these are owner-gated: connections are shared for use, and decrypted
# credentials never leave the server here - only catalog names, which aren't
# secret. Each level is fetched on demand, so cost scales with what the user
# opens rather than with the size of the database.


@connection_bp.get("/api/connections/{connection_id}/schemas")
def list_connection_schemas(connection_id: str):
    """Read the connection's schema names live from the source.

    One catalog query, made when a connection is picked for a job - the same
    on-demand treatment tables and columns already get. Nothing is cached on the
    connection row any more, so this cannot serve a stale list (migration 007).

    A connection failure is reported through describe_connection_error rather
    than as a 500: an unreachable database or expired credential is the
    operator's to fix, and the driver's own wording is not what they need to see.
    """
    try:
        schemas = saved_connection_service.list_schemas(connection_id)

        if schemas is None:
            return _error("Connection not found", 404)

        return {"ok": True, "schemas": schemas}
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:
        logger.exception("Failed to read schemas for '%s'", connection_id)
        return _error(describe_connection_error(exc), 400)


@connection_bp.post("/api/connections/{connection_id}/schemas/refresh")
def refresh_connection_schemas(connection_id: str):
    """Alias of the GET above, kept so an already-loaded SPA build does not 404.

    There is nothing left to refresh: the GET reads live every time. Retained
    only for compatibility with a browser still running a cached bundle from
    before migration 007.
    """
    return list_connection_schemas(connection_id)


@connection_bp.get("/api/connections/{connection_id}/tables")
def list_connection_tables(connection_id: str, schema: str = ""):
    """Return one schema's tables, fetched live."""
    try:
        if not schema.strip():
            return _error("schema is required", 400)

        tables = saved_connection_service.list_tables(connection_id, schema.strip())

        if tables is None:
            return _error("Connection not found", 404)

        return {"ok": True, "tables": tables}
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:
        logger.exception(
            "Failed to list tables for '%s' schema '%s'", connection_id, schema
        )
        return _error(describe_connection_error(exc), 400)


@connection_bp.get("/api/connections/{connection_id}/columns")
def list_connection_columns(connection_id: str, schema: str = "", table: str = ""):
    """Return one table's columns, fetched live."""
    try:
        if not schema.strip():
            return _error("schema is required", 400)

        if not table.strip():
            return _error("table is required", 400)

        columns = saved_connection_service.list_columns(
            connection_id, schema.strip(), table.strip()
        )

        if columns is None:
            return _error("Connection not found", 404)

        return {"ok": True, "columns": columns}
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:
        logger.exception(
            "Failed to list columns for '%s' %s.%s", connection_id, schema, table
        )
        return _error(describe_connection_error(exc), 400)
