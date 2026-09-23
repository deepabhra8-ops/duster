"""Coordinates job creation, execution, status retrieval, listing, logging, and results.

Jobs now have a draft phase: created with status='draft', given tables and a name,
then explicitly started. That exists so the V2 UI can attach a connection's metadata
scan and let the user pick schema/table/column rows before anything runs.
"""

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

# Background job execution (see JobService.submit_job). Bounded: each worker runs
# a whole job (build config, run the DQ engine, write results) start to finish, so
# an unbounded pool would let a flood of start requests run unlimited concurrent
# Spark work against one shared session.
_SUBMISSION_POOL = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="job-submit",
)

# Statuses in which a job is doing work and must not be deleted or restarted.
ACTIVE_STATUSES = ("queued", "running", "cancelling")


class JobService:
    """Coordinates job creation, execution, status, and reporting."""

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
        """Create and store a new queued job.

        The real params (including database credentials) are kept here: run_job()
        below needs them to execute, and download_staging() needs them again later
        to reconnect for a database-staging export. What must never happen is handing
        them back out verbatim over the API - see get_job()'s redaction instead.

        `owner` is the username that created the job (from the authenticated
        request) - see get_job()/request_cancel()/list_jobs() for how it's used
        to keep one user from reading or cancelling another user's job.
        """

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
        """Run a queued job on a background thread, without making the caller wait for it.

        run_job() is not fast: it builds the config and then runs the DQ engine
        itself to completion - potentially minutes for a large table - writing
        progress/status rows to Postgres as it goes. Doing that inside POST
        /api/job/{id}/start would leave the browser hanging until the whole run
        finished, which reads to the user as the server having crashed.

        The job row is already durably 'queued' before this is called, so the
        work here is recoverable: if this process dies mid-run, the job is left
        'running' with nothing left to finish it, and the startup sweep
        (job_runner.reset_interrupted_jobs) fails it explicitly next time the
        server starts, rather than leaving it to sit forever.
        """
        _SUBMISSION_POOL.submit(self._run_job_safely, job_id)

    def _run_job_safely(self, job_id: str) -> None:
        """Run a submission on the pool, making sure a failure is not silent."""
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
        """Build the job's config and run the DQ engine to completion.

        Blocking and slow - see submit_job(), which is what request handlers
        should call.
        """

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
        """Request cancellation of a queued or running job."""
        try:
            job = self.repository.get(job_id)

            if not job:
                return "not_found"

            if requester is not None and job.get("created_by") != requester:
                return "not_found"

            if job.get("status") not in ("queued", "running"):
                return "not_cancellable"

            # Two-stage: 'cancelling' now, terminal 'cancelled' once the running
            # engine actually notices and stops (job_runner.run's own handling
            # of JobCancelledError). The UI shows this intermediate state rather
            # than claiming the job stopped instantly. Guarded the same way: if
            # the job reached a terminal state between the read above and here,
            # there is nothing left to cancel.
            if not self.repository.transition(
                job_id, {"queued", "running"}, "cancelling"
            ):
                return "not_cancellable"

            self._log_job(job_id, "Cancellation requested by user")

            if job_runner.request_cancel(job_id):
                self._log_job(job_id, "Cancellation signal sent to the running job")
            else:
                # Nothing is actually executing this job yet - e.g. it is still
                # queued in the submission pool - so there is nothing to signal;
                # finish the cancellation immediately rather than leaving it stuck.
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
        """Return a job with its current status and report summary.

        This is what GET /api/job/<id> returns to the client verbatim, so `params`
        is redacted here - database credentials live in the stored job (see
        create_job) for internal use like run_job() and get_job_params(), but must
        never round-trip back out through this response.

        `requester` is the authenticated caller's username, checked against the
        job's `owner`. A job belonging to someone else is reported the same as a
        job that doesn't exist at all (empty dict, mapped to 404 by the route),
        rather than a 403 that would confirm the job id is valid - download_routes'
        per-job endpoints rely on this same check by calling get_job() first.
        """

        job = self.repository.get(job_id)

        if not job:
            return {}

        if requester is not None and job.get("created_by") != requester:
            return {}

        # Read the stored summary rather than re-parsing the report workbook on
        # every request - the summary is written once, when validation finishes.
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
            # has_profile means "profile-map rows exist to view/edit", which is what
            # the UI gates its results table on. has_profile_export separately means
            # "a workbook has been generated", which drives the download link.
            "has_profile": profile_map is not None,
            "has_profile_export": self._path_exists(
                job.get("profile_path")
            ),
            "has_staging": bool(staging_outputs),
            "summary": summary,
            "staging_outputs": staging_outputs,
            "started": job.get("started"),
            # Who created the job. Like error_message below, this column was always
            # populated (create_job writes the authenticated owner) and was already
            # being read here for the ownership check above - it just never made it
            # into the response, so the results pages had nothing to render for
            # "Started by". The jobs table has no separate created_at: started_at
            # carries a server_default of now() and the row is inserted at creation,
            # so `started` above serves as the creation timestamp.
            "created_by": job.get("created_by"),
            # Why a failed job failed. The column was already being written (by the
            # reconciler and the stuck-submission sweep) but never returned, so the
            # UI had nothing to show beyond the status itself.
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
        """Return a job's real, unredacted params for internal use only.

        Used where the app itself needs the credentials again after job creation -
        e.g. download_staging() reconnecting to export a database staging schema.
        Never expose this return value directly as an HTTP response; route it
        through get_job() (redacted) for anything the client sees.
        """

        job = self.repository.get(job_id)

        return job.get("params", {})

    def get_output_path(
        self,
        job_id: str,
        kind: str,
    ) -> str:
        """Return the stored filesystem path for a job's report or profile file."""

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
        """Return one page of jobs, filtered and paginated in SQL.

        Scoped to `requester`'s own jobs when given, so one authenticated user
        can't enumerate every other user's job ids through this listing - see
        get_job()'s matching per-job check.

        `step` and `status` back the V2 UI's separate Profile Mapper and Validator
        lists. Filtering moved into SQL because that UI polls this endpoint every
        1.4 seconds while any job is active, and the previous implementation loaded
        every job row into memory on each call.
        """
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
                    # The params snapshot preserves the type if a connection
                    # was deleted; the joined connection type fills legacy
                    # rows that predate the snapshot.
                    "databaseType": params.get("databaseType") or job.get("connection_db_type", ""),
                    "connectionName": job.get("connection_name", ""),
                    "sourceType": params.get("source_type", ""),
                    "progress": job.get("progress") or {"current": 0, "total": 0},
                    "created_by": job.get("created_by", ""),
                    # Retained for the legacy jobs table; the V2 lists filter
                    # explicitly instead of relying on an implicit archive cutoff.
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

    # =================================================================
    # DRAFT LIFECYCLE
    # =================================================================

    def create_draft_job(
        self,
        params: dict[str, Any],
        owner: str,
        name: str = "",
        description: str = "",
        step: str = "1",
        connection_id: str | None = None,
    ) -> str:
        """Create a job in 'draft' - persisted but not yet started.

        A draft carries its connection and (once set) its tables, so the user can
        assemble the run before anything executes. Returns the new job id.
        """
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
        """Replace a draft's table selection. Returns 'ok', 'not_found', or 'not_draft'."""
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
        """Rename / re-describe a job in any status. Returns 'ok' or 'not_found'."""
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
        """Start a draft job running.

        Returns 'ok', 'not_found', 'not_draft', 'no_tables', 'bad_tables',
        'no_connection', or 'no_profile_map'.
        """
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        if job.get("status") != "draft":
            return "not_draft"

        params = job.get("params") or {}

        if not params.get("tables"):
            return "no_tables"

        # Pre-flight, mirroring the one POST /api/run already performs for step 3.
        # Without it the only check was "tables is non-empty", so a draft missing
        # its connection or profile map was accepted, queued, and only then failed
        # deep inside the engine - with a message that named neither cause.
        problem = self._step3_preflight(job, params)

        if problem:
            logger.warning(
                "Refused to start job '%s': %s", job_id, problem
            )
            return problem

        # The status check and the write are one statement, so two concurrent
        # start requests cannot both get past it. Losing the race is a normal
        # outcome, not an error - the other request is already starting the job,
        # and running it twice would waste the second run's work entirely.
        if not self.repository.transition(job_id, {"draft"}, "queued"):
            return "not_draft"

        # Returns immediately: the job is queued in the database, and the actual
        # run happens in the background so the request does not wait on it.
        self.submit_job(job_id)
        return "ok"

    def _step3_preflight(
        self,
        job: dict[str, Any],
        params: dict[str, Any],
    ) -> str | None:
        """Return a failure reason if this draft cannot possibly run, else None.

        Only step 3 (validation) is checked, because it is the step with two
        required inputs - a profile map AND a live source - and the one where a
        half-configured draft was reaching the engine.
        """
        if str(job.get("step")) != "3":
            return None

        if any(not isinstance(table, dict) for table in params.get("tables", [])):
            return "bad_tables"

        source_type = params.get("source_type", "database")

        if source_type == "database":
            resolved = config_builder.resolve_connection(params)

            if not resolved.get("connectionDetails"):
                return "no_connection"

        # Either stored rows copied from a Profile Mapper job, or an uploaded
        # workbook that actually exists on disk.
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
        """Delete a job. Returns 'ok', 'not_found', or 'active' (still running)."""
        job = self._owned_job(job_id, requester)

        if job is None:
            return "not_found"

        if job.get("status") in ACTIVE_STATUSES:
            return "active"

        # profile_map_results / validation_results / profile_map_edits all cascade.
        self.repository.delete(job_id)
        logger.info("Deleted job '%s'", job_id)
        return "ok"

    # =================================================================
    # VALIDATOR DRAFTS AND PROFILE-MAP EXPORT
    # =================================================================

    def create_validator_draft(
        self,
        source_job_id: str,
        name: str,
        description: str,
        owner: str,
        lov_file: str | None = None,
    ) -> tuple[str | None, str]:
        """Build a step-3 draft from a completed Profile Mapper job.

        Copies the source's connection and tables. The profile map itself is not
        copied here - it is read fresh from the source job at start time, so a
        validator picks up edits made after it was created.

        Returns (job_id, "ok") or (None, reason).
        """
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
            # Consumed at start time to publish the edited rows for the engine.
            "profile_map_source_job_id": source_job_id,
        }

        # A LOV belongs to the job that was created with it, not to the upload
        # directory. Inheriting the source job's would silently validate this
        # run against a reference list someone chose for a different one.
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
        """Render the job's current profile-map rows to .xlsx and store it.

        Generated on demand from stored rows rather than at run time, which is what
        makes the download reflect the analyst's edits. Returns (filename, "ok") or
        (None, reason).
        """
        from services.profile_map_exporter import profile_map_exporter

        job = self._owned_job(job_id, requester)

        if job is None:
            return None, "not_found"

        stored = profile_map_repository.get(job_id)

        if stored is None:
            return None, "no_profile_map"

        workbook = profile_map_exporter.build(stored["rows"])
        filename = f"Source_DQ_Profile_Map_{job_id}.xlsx"

        # Storing the workbook is a CACHE, not the deliverable - the bytes are
        # already built at this point, so a storage failure must not cost the
        # user their download.
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
        """Return the job if it exists and belongs to `requester`, else None.

        Someone else's job is reported identically to a missing one, so the API
        never confirms that a job id is valid to a user who can't see it.
        """
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
        """Update fields on an existing job."""

        self.repository.update(
            job_id,
            **fields,
        )

    def _update_job(
        self,
        job_id: str,
        **fields: Any,
    ) -> None:
        """Internal callback used by PipelineService."""

        self.repository.update(
            job_id,
            **fields,
        )

    def _log_job(
        self,
        job_id: str,
        message: str,
    ) -> None:
        """Append a timestamped message to a job log."""

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
        """Return metadata for CSV files in the job staging directory."""
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
        """Return whether a configured filesystem path exists."""

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
