import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from repositories.profile_map_repository import ProfileMapVersionConflict
from core.config import MAX_UPLOAD_SIZE_BYTES
from routes.auth_routes import require_auth
from services.config_builder import config_builder
from services.job_service import job_service
from services.profile_map_service import profile_map_service
from services.profile_map_workbook_reader import profile_map_workbook_reader
from services.saved_connection_service import saved_connection_service
from services.upload_file_saver import UploadFileSaver
from utils.logger import get_logger


logger = get_logger(__name__)


job_bp = APIRouter()

RULEBOOK_MISSING_MESSAGE = (
    "No rulebook/profile map file found. Upload a Source-DQ-Profile-Map.xlsx "
    "before running Step 3. Please contact Administrator."
)

MALFORMED_TABLES_MESSAGE = (
    "Each selected table must be an object with a 'name'. "
    "Re-pick the source tables and try again."
)


def _tables_are_malformed(tables: list[Any]) -> bool:
    return any(
        not isinstance(table, dict) or not str(table.get("name", "")).strip()
        for table in tables
    )


def _duplicate_table_name(tables: list[dict[str, Any]]) -> str | None:
    seen: set[str] = set()

    for table in tables:
        name = str(table.get("name", "")).strip()

        if name.lower() in seen:
            return name

        seen.add(name.lower())

    return None


def _tables_problem(tables: list[Any]) -> str | None:
    if _tables_are_malformed(tables):
        return MALFORMED_TABLES_MESSAGE

    duplicate = _duplicate_table_name(tables)

    if duplicate is not None:
        return (
            f"More than one source table is named '{duplicate}'. "
            "Each table or file in a job needs a unique name."
        )

    return None


@job_bp.post("/api/run")
async def run_pipeline(
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        params = await request.json()
        params = params if isinstance(params, dict) else {}

        job_id = str(uuid.uuid4())

        step = str(params.get("step", "1"))

        if step == "3":
            profile_map_path = config_builder.resolve_profile_map_path(
                job_id,
                params,
            )
            if profile_map_path is None or not profile_map_path.is_file():
                logger.warning(
                    "Rejected Step 3 job: no rulebook/profile map found for '%s'",
                    username,
                )
                return JSONResponse(
                    {"error": RULEBOOK_MISSING_MESSAGE},
                    status_code=400,
                )

        job_service.create_job(job_id=job_id, params=params, owner=username)

        job_service.submit_job(job_id)

        logger.info("Triggered validation job '%s'", job_id)
        return {"job_id": job_id, "status": "queued"}
    except Exception:
        logger.exception("Failed to queue validation job")
        raise


@job_bp.post("/api/job/{job_id}/cancel")
def cancel_job(job_id, username: str = Depends(require_auth)):
    try:
        result = job_service.request_cancel(job_id, requester=username)

        if result == "not_found":
            logger.warning("Cancel requested for unknown job '%s'", job_id)
            return JSONResponse({"error": "Job not found"}, status_code=404)

        if result == "not_cancellable":
            logger.info("Cancel requested for non-running job '%s'", job_id)
            return JSONResponse({"error": "Job is not running"}, status_code=409)

        logger.info("Cancellation requested for job '%s'", job_id)
        return {"job_id": job_id, "status": "cancelled"}
    except Exception:
        logger.exception("Failed to cancel job '%s'", job_id)
        raise


@job_bp.get("/api/job/{job_id}")
def job_status(job_id, username: str = Depends(require_auth)):
    try:
        job = job_service.get_job(job_id, requester=username)

        if not job:
            logger.warning("Job '%s' not found", job_id)
            return JSONResponse({"error": "Job not found"}, status_code=404)

        logger.debug("Retrieved job status '%s'", job_id)
        return job
    except Exception:
        logger.exception("Failed to retrieve job '%s'", job_id)
        raise


@job_bp.get("/api/jobs")
def list_jobs(request: Request, username: str = Depends(require_auth)):
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
        logger.warning("Invalid job pagination parameters")
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

    sort_by = request.query_params.get(
        "sortBy",
        "started",
    )

    sort_order = request.query_params.get(
        "sortOrder",
        "desc",
    )

    step = request.query_params.get("step", "").strip()
    status = request.query_params.get("status", "").strip()
    db_type = request.query_params.get("dbType", "").strip()

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
        result = job_service.list_jobs(
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            requester=username,
            step=step,
            status=status,
            db_type=db_type,
        )
        logger.debug("Listed jobs page %s", page)
        return result
    except Exception:
        logger.exception("Failed to list jobs")
        raise


@job_bp.post("/api/jobs/draft")
async def create_draft(
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        connection_id = body.get("connection_id") or None
        source_type = body.get("source_type", "database")

        if source_type not in ("database", "flat_file", "csv"):
            source_type = "database"

        params: dict[str, Any] = {
            "step": str(body.get("step", "1")),
            "source_type": source_type,
            "tables": [],
        }

        if connection_id:
            resolved = saved_connection_service.get(connection_id)

            if resolved is None:
                return JSONResponse(
                    {"ok": False, "error": "Saved connection not found"},
                    status_code=400,
                )

            params["connection_id"] = connection_id
            params["databaseType"] = resolved.get("db_type", "")

        tables = body.get("tables")
        profile_map_file = body.get("profile_map_file")
        lov_file = body.get("lov_file")

        if profile_map_file and ("/" in profile_map_file or "\\" in profile_map_file or ".." in profile_map_file):
            return JSONResponse(
                {"ok": False, "error": "Invalid profile_map_file path"},
                status_code=400,
            )

        if lov_file and ("/" in lov_file or "\\" in lov_file or ".." in lov_file):
            return JSONResponse(
                {"ok": False, "error": "Invalid lov_file path"},
                status_code=400,
            )

        if isinstance(tables, list):
            problem = _tables_problem(tables)

            if problem:
                logger.warning(
                    "Rejected draft with invalid table entries from '%s': %s",
                    username,
                    problem,
                )
                return JSONResponse(
                    {"ok": False, "error": problem},
                    status_code=400,
                )

            params["tables"] = tables

        if profile_map_file:
            params["profile_map_file"] = profile_map_file

        if lov_file:
            params["lov_file"] = lov_file

        job_id = job_service.create_draft_job(
            params=params,
            owner=username,
            name=body.get("name", ""),
            description=body.get("description", ""),
            step=str(body.get("step", "1")),
            connection_id=connection_id,
        )

        return {"ok": True, "job_id": job_id, "status": "draft"}
    except Exception:
        logger.exception("Failed to create draft job")
        return JSONResponse(
            {"ok": False, "error": "Failed to create the job"},
            status_code=500,
        )


@job_bp.post("/api/jobs/validator-draft")
async def create_validator_draft(
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        source_job_id = str(body.get("source_job_id", "")).strip()

        if not source_job_id:
            return JSONResponse(
                {"ok": False, "error": "source_job_id is required"},
                status_code=400,
            )

        lov_file = body.get("lov_file")

        if lov_file and ("/" in lov_file or "\\" in lov_file or ".." in lov_file):
            return JSONResponse(
                {"ok": False, "error": "Invalid lov_file path"},
                status_code=400,
            )

        job_id, reason = job_service.create_validator_draft(
            source_job_id=source_job_id,
            name=body.get("name", ""),
            description=body.get("description", ""),
            owner=username,
            lov_file=lov_file,
        )

        if reason == "source_not_found":
            return JSONResponse(
                {"ok": False, "error": "Source job not found"},
                status_code=404,
            )

        messages = {
            "not_profile_mapper": "That job is not a Profile Mapper job",
            "source_not_done": "The source job has not finished yet",
            "no_profile_map": "The source job has no profile map results",
        }

        if reason != "ok":
            return JSONResponse(
                {"ok": False, "error": messages.get(reason, "Cannot use that job")},
                status_code=400,
            )

        return {"ok": True, "job_id": job_id, "status": "draft"}
    except Exception:
        logger.exception("Failed to create validator draft")
        return JSONResponse(
            {"ok": False, "error": "Failed to create the job"},
            status_code=500,
        )


@job_bp.patch("/api/job/{job_id}/tables")
async def update_job_tables(
    job_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}
        tables = body.get("tables")

        if not isinstance(tables, list):
            return JSONResponse(
                {"ok": False, "error": "tables must be a list"},
                status_code=400,
            )

        problem = _tables_problem(tables)

        if problem:
            logger.warning(
                "Rejected table entries for job '%s' from '%s': %s",
                job_id,
                username,
                problem,
            )
            return JSONResponse(
                {"ok": False, "error": problem},
                status_code=400,
            )

        result = job_service.update_tables(job_id, tables, requester=username)

        if result == "not_found":
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        if result == "not_draft":
            return JSONResponse(
                {"ok": False, "error": "Only a draft job's tables can be changed"},
                status_code=400,
            )

        return {"ok": True, "job_id": job_id, "tables": tables}
    except Exception:
        logger.exception("Failed to update tables for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to update tables"}, status_code=500
        )


@job_bp.patch("/api/job/{job_id}/details")
async def update_job_details(
    job_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}

        result = job_service.update_details(
            job_id,
            name=body.get("name"),
            description=body.get("description"),
            requester=username,
        )

        if result == "not_found":
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        return {"ok": True, "job_id": job_id}
    except Exception:
        logger.exception("Failed to update details for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to update the job"}, status_code=500
        )


@job_bp.post("/api/job/{job_id}/start")
def start_job(job_id: str, username: str = Depends(require_auth)):
    try:
        result = job_service.start_draft_job(job_id, requester=username)

        if result == "not_found":
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        if result == "not_draft":
            return JSONResponse(
                {"ok": False, "error": "Job has already been started"},
                status_code=400,
            )

        start_errors = {
            "no_tables": "Select at least one table before running",
            "bad_tables": MALFORMED_TABLES_MESSAGE,
            "no_connection": (
                "This job has no usable source connection. Its saved connection may "
                "have been deleted - re-create the job against an existing one."
            ),
            "no_profile_map": (
                "No profile map is available for this job. Pick a completed Profile "
                "Mapper job, or upload a mapping workbook, before running it."
            ),
        }

        if result in start_errors:
            return JSONResponse(
                {"ok": False, "error": start_errors[result]},
                status_code=400,
            )

        return {"ok": True, "job_id": job_id, "status": "queued"}
    except Exception:
        logger.exception("Failed to start job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to start the job"}, status_code=500
        )


@job_bp.delete("/api/job/{job_id}")
def delete_job(job_id: str, username: str = Depends(require_auth)):
    try:
        result = job_service.delete_job(job_id, requester=username)

        if result == "not_found":
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        if result == "active":
            return JSONResponse(
                {"ok": False, "error": "Cancel the job before deleting it"},
                status_code=409,
            )

        return {"ok": True, "job_id": job_id}
    except Exception:
        logger.exception("Failed to delete job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to delete the job"}, status_code=500
        )


@job_bp.post("/api/profile-map/inspect")
async def inspect_profile_map(
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        form = await request.form()
        file = form.get("file")
        if not file:
            return JSONResponse({"error": "No file uploaded"}, status_code=400)

        saver = UploadFileSaver()
        raw = await file.read()

        if len(raw) > MAX_UPLOAD_SIZE_BYTES:
            raise ValueError(
                f"File exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB limit"
            )

        await file.seek(0)

        saved = await saver.save(file, kind="profile_map")

        result = profile_map_workbook_reader.inspect(io.BytesIO(raw))
        tables = result.get("tables", [])

        if not tables:
            return JSONResponse(
                {
                    "error": (
                        "No tables found in this workbook. Each sheet needs a "
                        "'Column' (or 'Column Name') header with at least one "
                        "column listed under it."
                    )
                },
                status_code=400,
            )

        return {
            "ok": True,
            "filename": saved["filename"],
            "tables": tables,
        }
    except ValueError as exc:
        logger.warning("Rejected uploaded profile map: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        logger.exception("Failed to inspect uploaded profile map")
        return JSONResponse(
            {"error": "The workbook could not be stored or read. Please try again."},
            status_code=500,
        )



@job_bp.get("/api/job/{job_id}/profile-map")
def get_profile_map(job_id: str, username: str = Depends(require_auth)):
    try:
        job = job_service.get_job(job_id, requester=username)

        if not job:
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        stored = profile_map_service.get_results(job_id)

        if stored is None:
            return JSONResponse(
                {"ok": False, "error": "This job has no profile map results yet"},
                status_code=404,
            )

        return {
            "ok": True,
            "job_id": job_id,
            "job_name": job.get("name"),
            "rows": stored["rows"],
            "version": stored["version"],
            "failed_tables": stored.get("failed_tables") or [],
        }
    except Exception:
        logger.exception("Failed to read profile map for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to load the profile map"}, status_code=500
        )


@job_bp.patch("/api/job/{job_id}/profile-map")
async def update_profile_map(
    job_id: str,
    request: Request,
    username: str = Depends(require_auth),
):
    try:
        job = job_service.get_job(job_id, requester=username)

        if not job:
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        body = await request.json()
        body = body if isinstance(body, dict) else {}

        version = body.get("version")
        edits = body.get("edits")
        additions = body.get("additions", [])
        removals = body.get("removals", [])

        if not isinstance(version, int):
            return JSONResponse(
                {"ok": False, "error": "version must be an integer"},
                status_code=400,
            )

        if not isinstance(edits, list):
            return JSONResponse(
                {"ok": False, "error": "edits must be a list"}, status_code=400
            )

        if not isinstance(additions, list):
            return JSONResponse(
                {"ok": False, "error": "additions must be a list"}, status_code=400
            )

        if not isinstance(removals, list):
            return JSONResponse(
                {"ok": False, "error": "removals must be a list"}, status_code=400
            )

        result = profile_map_service.apply_edits(
            job_id=job_id,
            version=version,
            edits=edits,
            edited_by=username,
            additions=additions,
            removals=removals,
        )

        return {"ok": True, "rows": result["rows"], "version": result["version"]}
    except ProfileMapVersionConflict as conflict:
        return JSONResponse(
            {
                "ok": False,
                "error": str(conflict),
                "rows": conflict.current_rows,
                "version": conflict.current_version,
            },
            status_code=409,
        )
    except KeyError:
        return JSONResponse(
            {"ok": False, "error": "This job has no profile map results yet"},
            status_code=404,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception:
        logger.exception("Failed to update profile map for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to save the profile map"}, status_code=500
        )


@job_bp.post("/api/job/{job_id}/profile-map/export")
def export_profile_map(job_id: str, username: str = Depends(require_auth)):
    try:
        filename, reason = job_service.export_profile_map(job_id, requester=username)

        if reason == "not_found":
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        if reason == "no_profile_map":
            return JSONResponse(
                {"ok": False, "error": "This job has no profile map results yet"},
                status_code=404,
            )

        return {"ok": True, "filename": filename}
    except Exception:
        logger.exception("Failed to export profile map for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to export the profile map"},
            status_code=500,
        )


@job_bp.get("/api/job/{job_id}/profile-map/edits")
def get_profile_map_edits(job_id: str, username: str = Depends(require_auth)):
    try:
        job = job_service.get_job(job_id, requester=username)

        if not job:
            return JSONResponse(
                {"ok": False, "error": "Job not found"}, status_code=404
            )

        return {"ok": True, "edits": profile_map_service.list_edits(job_id)}
    except Exception:
        logger.exception("Failed to read profile-map edits for job '%s'", job_id)
        return JSONResponse(
            {"ok": False, "error": "Failed to load the edit history"},
            status_code=500,
        )
