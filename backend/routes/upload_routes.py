"""HTTP endpoints for uploading, listing, and previewing files, delegating processing to UploadService."""

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile
from fastapi.responses import JSONResponse

from services.upload_service import upload_service
from utils.logger import get_logger


logger = get_logger(__name__)


upload_bp = APIRouter()


@upload_bp.post("/api/upload")
async def upload_file(request: Request):
    """Receive one or more uploaded files."""

    try:
        form = await request.form()

        files = [
            item
            for item in form.getlist("file")
            if isinstance(item, UploadFile)
        ]

        kind = form.get(
            "kind",
            "data",
        )

        logger.info(
            "Upload request received: "
            "kind='%s', file_count=%d",
            kind,
            len(files),
        )

        result = await upload_service.save_files(
            files=files,
            kind=kind,
        )

        if not result.get("ok"):
            error = result.get(
                "error",
                "Upload failed",
            )

            logger.warning(
                "Upload failed: kind='%s', error='%s'",
                kind,
                error,
            )

            status_code = (
                400
                if error == "No file(s) provided"
                else 500
            )

            return JSONResponse(
                result,
                status_code=status_code,
            )

        logger.info(
            "Upload completed: "
            "kind='%s', uploaded_count=%d, error_count=%d",
            kind,
            len(result.get("uploaded", [])),
            len(result.get("errors", [])),
        )

        return result

    except Exception:
        logger.exception(
            "Unexpected upload route failure"
        )
        raise


@upload_bp.get("/api/uploads")
def list_uploads(request: Request):
    """Return uploaded files with filtering, sorting, and pagination."""

    try:
        page = int(
            request.query_params.get(
                "page",
                1,
            )
        )

        page_size = int(
            request.query_params.get(
                "pageSize",
                10,
            )
        )

    except ValueError:
        logger.warning("Invalid upload pagination parameters")
        return JSONResponse(
            {
                "error": "page and pageSize must be integers",
            },
            status_code=400,
        )

    search = request.query_params.get(
        "search",
        "",
    ).strip()

    file_type = request.query_params.get(
        "fileType",
        "",
    )

    sort_by = request.query_params.get(
        "sortBy",
        "created_at",
    )

    sort_order = request.query_params.get(
        "sortOrder",
        "desc",
    )

    include_archived = (
        request.query_params.get(
            "includeArchived",
            "false",
        ).lower()
        == "true"
    )

    if page < 1:
        return JSONResponse(
            {
                "error": "page must be greater than 0",
            },
            status_code=400,
        )

    if page_size < 1:
        return JSONResponse(
            {
                "error": "pageSize must be greater than 0",
            },
            status_code=400,
        )

    try:
        result = upload_service.list_uploads(
            page=page,
            page_size=page_size,
            search=search,
            file_type=file_type,
            sort_by=sort_by,
            sort_order=sort_order,
            include_archived=include_archived,
        )
        logger.debug("Listed uploads page %s", page)
        return result
    except Exception:
        logger.exception("Failed to list uploads")
        raise


@upload_bp.get("/api/uploads/preview")
def preview_upload(request: Request):
    """Return a preview of an uploaded CSV or Excel file."""

    kind = request.query_params.get(
        "kind",
        "data",
    )

    filename = request.query_params.get(
        "filename",
        "",
    )

    try:
        result = upload_service.preview_file(
            kind=kind,
            filename=filename,
        )
    except Exception:
        logger.exception("Failed to preview upload")
        raise

    if result.get("ok"):
        logger.debug("Previewed upload '%s'", filename)
        return result

    error = result.get(
        "error",
        "Could not preview file",
    )

    if error == "filename required":
        status_code = 400
    elif error == "File not found":
        status_code = 404
    elif error.startswith("Unsupported upload kind"):
        status_code = 400
    else:
        status_code = 500

    logger.warning("Upload preview failed for '%s': %s", filename, error)
    return JSONResponse(result, status_code=status_code)
