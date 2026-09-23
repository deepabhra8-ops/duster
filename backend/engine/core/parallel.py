from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Sequence, TypeVar

from utils.logger import get_logger


logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


DEFAULT_MAX_TABLE_WORKERS = 4

_JOB_GROUP_ID = "spark.jobGroup.id"
_JOB_DESCRIPTION = "spark.job.description"


@dataclass
class TaskOutcome:
    index: int
    item: Any
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def resolve_max_workers(config: Any = None) -> int:
    raw = None

    if config is not None:
        try:
            raw = config.get("max_table_workers")
        except AttributeError:
            raw = None

    if raw is None:
        raw = os.getenv("DQ_MAX_TABLE_WORKERS")

    try:
        workers = int(raw) if raw is not None else DEFAULT_MAX_TABLE_WORKERS
    except (TypeError, ValueError):
        logger.warning(
            "Invalid max_table_workers %r; falling back to %s",
            raw,
            DEFAULT_MAX_TABLE_WORKERS,
        )
        workers = DEFAULT_MAX_TABLE_WORKERS

    return max(1, workers)


def _current_job_group() -> tuple[str | None, str | None]:
    try:
        from engine.core.spark_session import get_spark_session

        context = get_spark_session().sparkContext
        return (
            context.getLocalProperty(_JOB_GROUP_ID),
            context.getLocalProperty(_JOB_DESCRIPTION),
        )
    except Exception:
        logger.debug("Could not read the current Spark job group", exc_info=True)
        return None, None


def _apply_job_group(group_id: str | None, description: str | None) -> None:
    if group_id is None:
        return

    try:
        from engine.core.spark_session import get_spark_session

        get_spark_session().sparkContext.setJobGroup(group_id, description or "")
    except Exception:
        logger.warning(
            "Could not set job group '%s' on a worker thread; cancelling this "
            "run may not stop its Spark jobs",
            group_id,
            exc_info=True,
        )


def run_in_parallel(
    items: Sequence[T],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    cancel_event: threading.Event | None = None,
    description: str = "task",
) -> list[TaskOutcome]:
    if not items:
        return []

    workers = max(1, min(max_workers, len(items)))

    if workers == 1:
        return _run_sequentially(items, worker, cancel_event, description)

    group_id, group_description = _current_job_group()

    if group_id is None:
        logger.warning(
            "No Spark job group is set; a cancellation request may not stop "
            "in-flight %s jobs",
            description,
        )

    def run_one(index: int, item: T) -> TaskOutcome:
        _apply_job_group(group_id, group_description)

        if cancel_event is not None and cancel_event.is_set():
            return TaskOutcome(index=index, item=item, error=_cancelled())

        try:
            return TaskOutcome(index=index, item=item, value=worker(item))
        except BaseException as exc:
            return TaskOutcome(index=index, item=item, error=exc)

    logger.info(
        "Running %s %s(s) with up to %s workers",
        len(items),
        description,
        workers,
    )

    try:
        from pyspark.util import inheritable_thread_target

        target = inheritable_thread_target(run_one)
    except Exception:
        logger.debug("inheritable_thread_target unavailable; using the raw target", exc_info=True)
        target = run_one

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"dq-{description}") as pool:
        outcomes = list(pool.map(target, range(len(items)), items))

    outcomes.sort(key=lambda outcome: outcome.index)
    return outcomes


def _run_sequentially(
    items: Sequence[T],
    worker: Callable[[T], R],
    cancel_event: threading.Event | None,
    description: str,
) -> list[TaskOutcome]:
    outcomes: list[TaskOutcome] = []

    for index, item in enumerate(items):
        if cancel_event is not None and cancel_event.is_set():
            outcomes.append(TaskOutcome(index=index, item=item, error=_cancelled()))
            continue

        try:
            outcomes.append(TaskOutcome(index=index, item=item, value=worker(item)))
        except BaseException as exc:
            outcomes.append(TaskOutcome(index=index, item=item, error=exc))

    return outcomes


def _cancelled() -> BaseException:
    from utils.job_cancellation import JobCancelledError

    return JobCancelledError("Job cancelled by user")
