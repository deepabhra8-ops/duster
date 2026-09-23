from __future__ import annotations

import threading
from typing import Any, Callable

from repositories.job_repository import JobRepository
from repositories.profile_map_repository import profile_map_repository
from repositories.validation_result_repository import validation_result_repository
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)

_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

_INTERRUPTIBLE_STATUSES = ("queued", "running", "cancelling")


def request_cancel(job_id: str) -> bool:
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
