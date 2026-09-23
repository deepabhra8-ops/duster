import io
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from core.storage_layout import get_upload_file_path
from routes.auth_routes import require_auth
from services.job_service import job_service
from services.staging_export_service import (
    StagingExportError,
    staging_export_service,
)
from utils.logger import get_logger


logger = get_logger(__name__)


download_bp = APIRouter()

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@download_bp.get("/api/uploads/download")
def download_upload(request: Request, username: str = Depends(require_auth)):
    kind = request.query_params.get(
        "kind",
        "data",
    )

    filename = request.query_params.get(
        "filename",
        "",
    )

    if not filename:
        logger.warning("Upload download requested without filename")
        return JSONResponse(
            {
                "error": "filename required",
            },
            status_code=400,
        )

    try:
        file_path = get_upload_file_path(
            kind,
            filename,
        )
    except ValueError as exc:
        return JSONResponse(
            {
                "error": str(exc),
            },
            status_code=400,
        )

    if not file_path.exists():
        return JSONResponse(
            {
                "error": "File not found",
            },
            status_code=404,
        )

    logger.info("Serving uploaded file '%s'", file_path.name)
    return FileResponse(file_path, filename=file_path.name)


@download_bp.get("/api/job/{job_id}/download/{kind}")
def download_job_output(
    job_id: str,
    kind: str,
    username: str = Depends(require_auth),
):
    try:
        job = job_service.get_job(job_id, requester=username)
    except Exception:
        logger.exception("Failed to retrieve job '%s' for download", job_id)
        raise

    if not job:
        logger.warning("Job '%s' not found for download", job_id)
        return JSONResponse(
            {
                "error": "Job not found",
            },
            status_code=404,
        )

    if kind == "report":
        filename = f"DQ_Report_{job_id}.xlsx"
    elif kind == "profile":
        filename = f"Source_DQ_Profile_Map_{job_id}.xlsx"

        _, reason = job_service.export_profile_map(job_id, requester=username)
        if reason not in ("ok", "ok_uncached", "no_profile_map"):
            logger.warning(
                "Failed to regenerate profile map for job '%s' before download: %s",
                job_id,
                reason,
            )

        workbook = getattr(job_service, "last_exported_workbook", None)

        if reason in ("ok", "ok_uncached") and workbook:
            logger.info("Serving freshly generated profile map for job '%s'", job_id)
            return StreamingResponse(
                io.BytesIO(workbook),
                media_type=(
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
    else:
        return JSONResponse(
            {
                "error": "Unknown kind",
            },
            status_code=400,
        )

    path = job_service.get_output_path(job_id, kind)

    if not path:
        return JSONResponse(
            {
                "error": "File not ready",
            },
            status_code=404,
        )

    file_path = Path(path)

    if not file_path.exists():
        return JSONResponse(
            {
                "error": "File not ready",
            },
            status_code=404,
        )

    logger.info("Serving job '%s' %s output", job_id, kind)
    return FileResponse(file_path, filename=filename, media_type=XLSX_MEDIA_TYPE)


@download_bp.get("/api/job/{job_id}/staging/download")
def download_staging(
    job_id: str,
    username: str = Depends(require_auth),
):
    try:
        job = job_service.get_job(job_id, requester=username)
    except Exception:
        logger.exception("Failed to retrieve job '%s' for staging download", job_id)
        raise

    if not job:
        return JSONResponse(
            {
                "error": "Job not found",
            },
            status_code=404,
        )

    try:
        archive = staging_export_service.export(
            job_id,
            job_service.get_job_params(job_id),
        )
    except StagingExportError as exc:
        logger.warning(
            "Staging export failed for job '%s': %s",
            job_id,
            exc,
        )
        return JSONResponse(
            {
                "error": str(exc),
            },
            status_code=exc.status_code,
        )

    logger.info("Serving staging archive for job '%s'", job_id)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Staging_{job_id}.zip"'},
    )


@download_bp.get("/api/sample-csv")
def sample_csv():
    content = (
        "CustomerID,Name,Email,Age,Country\n"
        "1,Alice,alice@example.com,28,India\n"
        "2,,bobexample.com,-2,USA\n"
        "3,Charlie,,35,UK\n"
        "4,David,david@example.com,200,Unknown\n"
    )

    buffer = io.BytesIO(
        content.encode("utf-8")
    )

    buffer.seek(0)

    logger.debug("Serving sample CSV")
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_data.csv"'},
    )


@download_bp.get("/api/sample-lov")
def sample_lov():
    content = (
        "policy.policy_status,policy.policy_type,"
        "claim.claim_status,claim.claim_type,"
        "customer.gender,customer.state\n"
        "Active,Auto,Open,Collision,Male,CA\n"
        "Expired,Home,Closed,Theft,Female,NY\n"
        "Cancelled,Life,Pending,Fire,Non-binary,TX\n"
        ",,Reopened,,,\n"
    )

    buffer = io.BytesIO(
        content.encode("utf-8")
    )

    buffer.seek(0)

    logger.debug("Serving sample LOV")
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="samplelov.csv"'},
    )
