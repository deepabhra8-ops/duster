import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from core.config import JOB_ARCHIVE_THRESHOLD
from services import job_runner
from services.config_builder import config_builder
from repositories.job_repository import JobRepository
from repositories.profile_map_repository import profile_map_repository
from repositories.validation_result_repository import validation_result_repository
from services.pipeline_service import pipeline_service
from utils.logger import get_logger
from common.security.secret_redaction import redact_secrets


logger = get_logger(__name__)

_SUBMISSION_POOL = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="job-submit",
)

ACTIVE_STATUSES = ("queued", "running", "cancelling")


class JobService:
    def __init__(
        self,
        repository: JobRepository,
    ) -> None:
        self.repository = repository

    def create_job(
        self,
        job_id: str,
        params: dict[str, Any],
        owner: str | None = None,
    ) -> dict[str, Any]:
        job = {
            "status": "queued",
            "log": [],
            "report_path": None,
            "profile_path": None,
            "staging_path": None,
            "progress": {"current": 0, "total": 0},
            "started": datetime.now().isoformat(),
            "params": params,
            "created_by": owner,
        }

        self.repository.create(
            job_id,
            job,
        )

        return job.copy()

    def submit_job(
        self,
        job_id: str,
    ) -> None:
        _SUBMISSION_POOL.submit(self._run_job_safely, job_id)

    def _run_job_safely(self, job_id: str) -> None:
        try:
            self.run_job(job_id)
        except Exception:
            logger.exception("Background submission failed for job '%s'", job_id)

            try:
                self._log_job(job_id, "ERROR: the job could not be started")
                self.repository.transition(job_id, {"queued"}, "error")
            except Exception:
                logger.exception("Could not record the submission failure for '%s'", job_id)

    def run_job(
        self,
        job_id: str,
    ) -> None:
        job = self.repository.get(job_id)

        if not job:
            raise KeyError(
                f"Job not found: {job_id}"
            )

        params = job.get("params", {})

        pipeline_service.run_job(
            job_id=job_id,
            params=params,
            update_job=self._update_job,
            log_job=self._log_job,
            repository=self.repository,
        )

    def request_cancel(
        self,
        job_id: str,
        requester: str | None = None,
    ) -> str:
        try:
            job = self.repository.get(job_id)

            if not job:
                return "not_found"

            if requester is not None and job.get("created_by") != requester:
                return "not_found"

            if job.get("status") not in ("queued", "running"):
                return "not_cancellable"

            if not self.repository.transition(
                job_id, {"queued", "running"}, "cancelling"
            ):
                return "not_cancellable"

            self._log_job(job_id, "Cancellation requested by user")

            if job_runner.request_cancel(job_id):
                self._log_job(job_id, "Cancellation signal sent to the running job")
            else:
                self.repository.transition(job_id, {"cancelling"}, "cancelled")
                self._log_job(job_id, "Job cancelled before it started running")

            return "cancelling"
        except Exception as exc:
            logger.exception("CRITICAL CRASH in request_cancel: %s", exc)
            self._log_job(job_id, f"Internal Error during cancellation: {exc}")
            return "cancelling"

    def get_job(
        self,
        job_id: str,
        requester: str | None = None,
    ) -> dict[str, Any]:
        job = self.repository.get(job_id)

        if not job:
            return {}

        if requester is not None and job.get("created_by") != requester:
            return {}

        stored_result = validation_result_repository.get(job_id)
        summary = stored_result["summary"] if stored_result else {}

        staging_outputs = self._get_staging_outputs(
            job_id
        )

        profile_map = profile_map_repository.get(job_id)

        return {
            "job_id": job_id,
            "name": job.get("name"),
            "description": job.get("description"),
            "status": job.get("status"),
            "log": job.get("log", []),
            "progress": job.get("progress") or {"current": 0, "total": 0},
            "has_report": self._path_exists(
                job.get("report_path")
            ),
            "has_profile": profile_map is not None,
            "has_profile_export": self._path_exists(
                job.get("profile_path")
            ),
            "has_staging": bool(staging_outputs),
            "summary": summary,
            "staging_outputs": staging_outputs,
            "started": job.get("started"),
            "created_by": job.get("created_by"),
            "error_message": job.get("error_message"),
            "step": job.get("step"),
            "connection_id": job.get("connection_id"),
            "source_job_id": job.get("source_job_id"),
            "params": redact_secrets(
                job.get("params", {})
            ),
        }

    def get_job_params(
        self,
        job_id: str,
    ) -> dict[str, Any]:
        job = self.repository.get(job_id)

        return job.get("params", {})

    def get_output_path(
        self,
        job_id: str,
        kind: str,
    ) -> str:
        field = {
            "report": "report_path",
            "profile": "profile_path",
        }.get(kind)

        if field is None:
            return ""

        job = self.repository.get(job_id)

        return job.get(field) or ""

    def list_jobs(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str = "",
        sort_by: str = "started",
        sort_order: str = "desc",
        requester: str | None = None,
        step: str = "",
        status: str = "",
        db_type: str = "",
    ) -> dict[str, Any]:
        rows, total = self.repository.list_page(
            owner=requester,
            step=step,
            status=status,
            db_type=db_type,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

        offset = max(page - 1, 0) * page_size

        jobs = []

        for index, job in enumerate(rows):
            params = job.get("params") or {}

            jobs.append(
                {
                    "job_id": job.get("job_id"),
                    "name": job.get("name"),
                    "description": job.get("description"),
                    "status": job.get("status", ""),
                    "started": job.get("started"),
                    "step": job.get("step"),
                    "project": params.get("project_name", "–"),
                    "databaseType": params.get("databaseType") or job.get("connection_db_type", ""),
                    "connectionName": job.get("connection_name", ""),
                    "sourceType": params.get("source_type", ""),
                    "progress": job.get("progress") or {"current": 0, "total": 0},
                    "created_by": job.get("created_by", ""),
                    "archived": (offset + index) >= JOB_ARCHIVE_THRESHOLD,
                }
            )

        total_pages = (
            (total + page_size - 1) // page_size
            if page_size
            else 1
        )

        return {
            "jobs": jobs,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": total_pages,
        }

    def create_draft_job(
        self,
        params: dict[str, Any],
        owner: str,
        name: str = "",
        description: str = "",
        step: str = "1",
        connection_id: str | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())

        self.repository.create(
            job_id,
            {
                "status": "draft",
                "log": [],
                "progress": {"current": 0, "total": 0},
                "params": params,
                "created_by": owner,
                "name": (name or "").strip() or None,
                "description": (description or "").strip() or None,
                "step": str(step),
                "connection_id": connection_id,
                "source_job_id": params.get("source_job_id"),
            },
        )

        self._log_job(job_id, "Draft created")
        logger.info("Created draft job '%s' (step %s)", job_id, step)
        return job_id

    def update_tables(
        self,
        job_id: str,
        tables: list[dict[str, Any]],
        requester: str | None = None,
    ) -> str:
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        if job.get("status") != "draft":
            return "not_draft"

        params = dict(job.get("params") or {})
        params["tables"] = tables

        self.repository.update(job_id, params=params)
        self._log_job(job_id, f"Selected {len(tables)} table(s)")
        return "ok"

    def update_details(
        self,
        job_id: str,
        name: str | None,
        description: str | None,
        requester: str | None = None,
    ) -> str:
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        fields: dict[str, Any] = {}

        if name is not None:
            fields["name"] = str(name).strip() or None

        if description is not None:
            fields["description"] = str(description).strip() or None

        if fields:
            self.repository.update(job_id, **fields)

        return "ok"

    def start_draft_job(
        self,
        job_id: str,
        requester: str | None = None,
    ) -> str:
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        if job.get("status") != "draft":
            return "not_draft"

        params = job.get("params") or {}

        if not params.get("tables"):
            return "no_tables"

        problem = self._step3_preflight(job, params)

        if problem:
            logger.warning(
                "Refused to start job '%s': %s", job_id, problem
            )
            return problem

        if not self.repository.transition(job_id, {"draft"}, "queued"):
            return "not_draft"

        self.submit_job(job_id)
        return "ok"

    def _step3_preflight(
        self,
        job: dict[str, Any],
        params: dict[str, Any],
    ) -> str | None:
        if str(job.get("step")) != "3":
            return None

        if any(not isinstance(table, dict) for table in params.get("tables", [])):
            return "bad_tables"

        source_type = params.get("source_type", "database")

        if source_type == "database":
            resolved = config_builder.resolve_connection(params)

            if not resolved.get("connectionDetails"):
                return "no_connection"

        if params.get("profile_map_source_job_id"):
            return None

        profile_map_file = params.get("profile_map_file", "")

        if not profile_map_file:
            return "no_profile_map"

        profile_map_path = config_builder.resolve_profile_map_path(
            job.get("job_id", ""), params
        )

        if profile_map_path is None or not profile_map_path.is_file():
            return "no_profile_map"

        return None

    def delete_job(
        self,
        job_id: str,
        requester: str | None = None,
    ) -> str:
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        if job.get("status") in ACTIVE_STATUSES:
            return "active"

        self.repository.delete(job_id)
        logger.info("Deleted job '%s'", job_id)
        return "ok"

    def create_validator_draft(
        self,
        source_job_id: str,
        name: str,
        description: str,
        owner: str,
        lov_file: str | None = None,
    ) -> tuple[str | None, str]:
        source = self._owned_job(source_job_id, owner)

        if source is None:
            return None, "source_not_found"

        if str(source.get("step")) != "1":
            return None, "not_profile_mapper"

        if source.get("status") != "done":
            return None, "source_not_done"

        if profile_map_repository.get(source_job_id) is None:
            return None, "no_profile_map"

        source_params = dict(source.get("params") or {})

        params = {
            **source_params,
            "step": "3",
            "run_mode": source_params.get("run_mode", 1),
            "source_job_id": source_job_id,
            "profile_map_source_job_id": source_job_id,
        }

        params.pop("lov_file", None)

        if lov_file:
            params["lov_file"] = lov_file

        job_id = self.create_draft_job(
            params=params,
            owner=owner,
            name=name,
            description=description,
            step="3",
            connection_id=source.get("connection_id"),
        )

        self.repository.update(job_id, source_job_id=source_job_id)

        self._log_job(
            job_id, f"Validator draft created from profile mapper job {source_job_id}"
        )
        return job_id, "ok"

    def export_profile_map(
        self,
        job_id: str,
        requester: str | None = None,
    ) -> tuple[str | None, str]:
        from services.profile_map_exporter import profile_map_exporter

        job = self._owned_job(job_id, requester)

        if job is None:
            return None, "not_found"

        stored = profile_map_repository.get(job_id)

        if stored is None:
            return None, "no_profile_map"

        workbook = profile_map_exporter.build(stored["rows"])
        filename = f"Source_DQ_Profile_Map_{job_id}.xlsx"

        self.last_exported_workbook = workbook

        from core.storage_layout import get_profile_map_job_path

        try:
            path = get_profile_map_job_path(job_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(workbook)
            self.repository.update(job_id, profile_path=str(path))
        except Exception:
            logger.warning(
                "Could not cache the profile map for '%s' to disk; serving the "
                "generated workbook directly",
                job_id,
                exc_info=True,
            )
            return filename, "ok_uncached"

        self._log_job(job_id, "Profile map exported")
        return filename, "ok"

    def _owned_job(
        self,
        job_id: str,
        requester: str | None,
    ) -> dict[str, Any] | None:
        job = self.repository.get(job_id)

        if not job:
            return None

        if requester is not None and job.get("created_by") != requester:
            return None

        return job

    def update_job(
        self,
        job_id: str,
        **fields: Any,
    ) -> None:
        self.repository.update(
            job_id,
            **fields,
        )

    def _update_job(
        self,
        job_id: str,
        **fields: Any,
    ) -> None:
        self.repository.update(
            job_id,
            **fields,
        )

    def _log_job(
        self,
        job_id: str,
        message: str,
    ) -> None:
        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        line = f"[{timestamp}] {message}"

        self.repository.append_log(
            job_id,
            line,
        )

        print(line)

    def _get_staging_outputs(
        self,
        job_id: str,
    ) -> list[dict[str, str]]:
        from core.storage_layout import get_staging_dir

        staging_dir = get_staging_dir(job_id)

        if not staging_dir.is_dir():
            return []

        outputs = []

        for path in sorted(staging_dir.iterdir()):
            if not path.is_file():
                continue

            if path.suffix.lower() != ".csv":
                continue

            table = path.name.replace(
                "_clean.csv",
                "",
            ).replace(
                ".csv",
                "",
            )

            outputs.append(
                {
                    "table": table,
                    "type": "csv",
                    "filename": path.name,
                    "download_url": (
                        f"/api/job/{job_id}/staging/download"
                    ),
                }
            )

        return outputs

    @staticmethod
    def _path_exists(
        path: Any,
    ) -> bool:
        if not path:
            return False

        try:
            from pathlib import Path

            return Path(str(path)).exists()
        except (TypeError, ValueError, OSError):
            return False


job_service = JobService(
    JobRepository()
)
