"""HTTP endpoints for LOV (List of Values) management: listing uploaded LOV files and deleting them."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.lov_service import lov_service
from utils.logger import get_logger


logger = get_logger(__name__)


lov_bp = APIRouter()


@lov_bp.get("/api/lovs")
def list_lovs():
    """Return every uploaded LOV file and the LOV names each one defines.

    Each entry: { file, display_name, lovs: [{ name, values_count }] }.
    `file` is the stored filename (UUID-prefixed) that delete takes,
    `display_name` is the name the user uploaded it under,
    and `lovs` is one entry per column in the CSV - a LOV file is wide, so a
    single upload can define every LOV a job's DQ8 rules reference.
    """
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
    """Return one LOV file's entry - same shape as a row of the list."""
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
    """Delete a single LOV CSV by its stored filename, local or in S3."""
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
