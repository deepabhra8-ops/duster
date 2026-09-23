from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.lov_service import lov_service
from utils.logger import get_logger


logger = get_logger(__name__)


lov_bp = APIRouter()


@lov_bp.get("/api/lovs")
def list_lovs():
    try:
        files = lov_service.list_lov_files()
        logger.debug("Listed %d LOV files", len(files))
        return {"ok": True, "data": files}

    except Exception:
        logger.exception("Failed to list LOVs")
        return JSONResponse(
            {"ok": False, "error": "Failed to list LOV files"},
            status_code=500,
        )


@lov_bp.get("/api/lovs/{filename}")
def get_lov(filename: str):
    try:
        entry = lov_service.get_lov_file(filename)

    except Exception:
        logger.exception("Failed to read LOV '%s'", filename)
        return JSONResponse(
            {"ok": False, "error": "Failed to read LOV file"},
            status_code=500,
        )

    if entry is None:
        return JSONResponse(
            {"ok": False, "error": f"LOV file '{filename}' not found"},
            status_code=404,
        )

    return {"ok": True, "data": entry}


@lov_bp.delete("/api/lovs/{filename}")
def delete_lov(filename: str):
    try:
        deleted = lov_service.delete_lov_file(filename)

    except ValueError:
        logger.warning("Rejected LOV delete for invalid filename '%s'", filename)
        return JSONResponse(
            {"ok": False, "error": "Invalid filename"},
            status_code=400,
        )

    except Exception:
        logger.exception("Failed to delete LOV '%s'", filename)
        return JSONResponse(
            {"ok": False, "error": "Failed to delete LOV file"},
            status_code=500,
        )

    if not deleted:
        return JSONResponse(
            {"ok": False, "error": f"LOV file '{filename}' not found"},
            status_code=404,
        )

    logger.info("Deleted LOV file: %s", filename)
    return {"ok": True}
