from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from routes.auth_routes import require_auth
from services.saved_connection_service import ConnectionPermissionError
from services.ingestion_pattern_service import ingestion_pattern_service
from utils.logger import get_logger


logger = get_logger(__name__)


ingestion_bp = APIRouter()


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@ingestion_bp.get("/api/connections/{connection_id}/ingestion")
def get_ingestion_config(connection_id: str):
    try:
        preview = ingestion_pattern_service.preview(connection_id)

        if preview is None:
            return _error("Connection not found", 404)

        return {"ok": True, "data": preview}
    except Exception:
        logger.exception("Failed to read ingestion config for '%s'", connection_id)
        return _error("Failed to load ingestion configuration", 500)


@ingestion_bp.patch("/api/connections/{connection_id}/ingestion")
async def save_ingestion_config(
    connection_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        saved = ingestion_pattern_service.save(
            connection_id=connection_id,
            username=username,
            latency_requirement=body.get("latencyRequirement", ""),
            scheduling_ownership=body.get("schedulingOwnership", ""),
        )

        if saved is None:
            return _error("Connection not found", 404)

        return {"ok": True, "data": saved}
    except ConnectionPermissionError as exc:
        return _error(str(exc), 403)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to save ingestion config for '%s'", connection_id)
        return _error("Failed to save ingestion configuration", 500)
