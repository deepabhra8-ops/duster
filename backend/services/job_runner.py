"""Runs the DQ engine (Profile Mapper / Validator) in-process for one job.

This is what used to be an AWS Glue run: instead of uploading a config to S3 and
starting a remote job, the engine now runs directly, synchronously, in a
background thread of this process (see pipeline_service.py). Progress and
results are written through the same repositories the rest of the app already
uses - JobRepository, ProfileMapRepository, ValidationResultRepository - rather
than a separate connection, since nothing here is remote any more.

`config_builder.build()` already resolves every path in its config dict to
somewhere on this machine (see core/storage_layout.py) - the S3 downloads/uploads and
path-rewriting the old Glue entrypoint needed only existed to bridge a *remote*
worker to this machine's `runtime/` directory, and none of that applies here.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from repositories.job_repository import JobRepository
from repositories.profile_map_repository import profile_map_repository
from repositories.validation_result_repository import validation_result_repository
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)

# One cancellation flag per in-flight job, checked by the engine's own per-table
# loops (see DQProfileMapper / DQValidator). Replaces the old S3 `.cancelled`
# marker file + polling thread - cancelling now just means setting a flag in this
# same process's memory.
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

# Statuses reset_interrupted_jobs() treats as abandoned when the process starts.
_INTERRUPTIBLE_STATUSES = ("queued", "running", "cancelling")


def request_cancel(job_id: str) -> bool:
    """Signal a running job to stop. Returns whether an in-flight job was found."""
    with _cancel_lock:
        event = _cancel_events.get(job_id)

    if event is None:
        return False

    event.set()

    try:
        from engine.core.spark_session import get_spark_session

        spark_context = get_spark_session().sparkContext
        spark_context.cancelJobGroup(job_id)
    except Exception:
        logger.warning(
            "Could not cancel the Spark job group for '%s'", job_id, exc_info=True
        )

    return True


def reset_interrupted_jobs(repository: JobRepository) -> int:
    """Mark any job left active by a previous process run as failed.

    Called once at startup (see app.py's lifespan). Execution now lives entirely
    in this process's memory, in a thread pool - a job still 'queued', 'running'
    or 'cancelling' when the process last stopped was not paused, it was
    abandoned mid-run; nothing is coming back to finish it. Returns how many jobs
    were settled.
    """
    settled = 0

    for status in _INTERRUPTIBLE_STATUSES:
        for job in repository.list_by_statuses((status,), limit=1000):
            moved = repository.transition(
                job["job_id"],
                {status},
                "error",
                error="Interrupted by a server restart. Start the job again.",
            )

            if moved:
                settled += 1

    if settled:
        logger.warning(
            "Marked %s job(s) as failed after a restart interrupted them", settled
        )

    return settled


def run(
    job_id: str,
    config: dict[str, Any],
    step: str,
    repository: JobRepository,
    log_job: Callable[[str, str], None],
) -> None:
    """Run a job's engine step to completion. Blocking - call from a worker thread.

    Mirrors the step-1 / step-3 branch that used to run inside
    glue/dq_glue_job.py's main(). On success, transitions the job straight to
    'done' here (previously the Glue run's own responsibility, since the web
    tier had no way to know when a remote run finished). On failure, lets the
    exception propagate so pipeline_service.run_job()'s existing handler logs
    the traceback and marks the job 'error' - except a cooperative cancellation
    (JobCancelledError), which is handled here as 'cancelled'.
    """
    from engine.dq_profile_mapper import DQProfileMapper
    from engine.dq_validator import DQValidator
    from engine.profile_map.profile_map_rows import build_rows
    from engine.profile_map.normalize_rows import normalize_rows
    from engine.reporting.validation_summary import build_summary

    cancel_event = threading.Event()

    with _cancel_lock:
        _cancel_events[job_id] = cancel_event

    def report_progress(current: int, total: int) -> None:
        try:
            repository.update(job_id, progress={"current": current, "total": total})
        except Exception:
            logger.warning(
                "Failed to record progress for job '%s'", job_id, exc_info=True
            )

    try:
        if step == "1":
            log_job(job_id, "Running Step 1 — Profile Mapper")

            mapper = DQProfileMapper(
                config=config,
                progress_callback=report_progress,
                cancel_event=cancel_event,
            )

            # No workbook is written here. The rows are stored so the user can
            # review and edit them; the .xlsx is generated on demand later from
            # those (possibly edited) rows - see JobService.export_profile_map.
            profile_map = mapper.generate_profile_map()
            rows = normalize_rows(build_rows(profile_map))
            failed_tables = [
                {"table": name, "error": error}
                for name, error in mapper.failed_tables.items()
            ]

            profile_map_repository.save(job_id, rows, failed_tables)
            log_job(job_id, f"Profile map built ({len(rows)} columns)")

            for failed in failed_tables:
                log_job(job_id, f"Skipped '{failed['table']}': {failed['error']}")

            repository.transition(job_id, {"running"}, "done")

        elif step == "3":
            log_job(job_id, "Running Step 3 — DQ Validator")

            # Two supported sources, in priority order: rows stored by the
            # source Profile Mapper job (including any analyst edits), or a
            # workbook the user uploaded - already resolved onto local disk in
            # config["profile_map_file"] by config_builder.
            source_job_id = config.get("profile_map_source_job_id")

            if source_job_id:
                stored = profile_map_repository.get(source_job_id)
                profile_map_rows = stored["rows"] if stored else []

                if profile_map_rows:
                    config["profile_map_rows"] = profile_map_rows
                    log_job(
                        job_id,
                        f"Loaded {len(profile_map_rows)} profile-map row(s) "
                        f"from job {source_job_id}",
                    )

            validator = DQValidator(
                config=config,
                progress_callback=report_progress,
                cancel_event=cancel_event,
            )

            try:
                from engine.core.spark_session import get_spark_session

                get_spark_session().sparkContext.setJobGroup(
                    job_id, f"DQ Validator {job_id}"
                )
            except Exception:
                pass

            # One Spark pass produces both the workbook and the in-memory result
            # the stored summary is built from - no re-parsing the report just written.
            validation_result, report_path = validator.validate_and_report()

            validation_result_repository.save(job_id, build_summary(validation_result))

            from core.storage_layout import get_staging_dir

            staging_dir = get_staging_dir(job_id)

            repository.transition(
                job_id,
                {"running"},
                "done",
                report_path=str(report_path),
                staging_path=str(staging_dir) if staging_dir.is_dir() else None,
            )

        else:
            raise ValueError(f"Unknown step: {step}")

    except JobCancelledError:
        log_job(job_id, "Job cancelled by user")
        repository.transition(job_id, {"running", "cancelling"}, "cancelled")

    finally:
        with _cancel_lock:
            _cancel_events.pop(job_id, None)
