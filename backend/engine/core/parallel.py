"""Bounded parallel execution of per-table work, shared by profiling and validation.

Both engines used to walk their tables strictly one at a time. For a handful of
large tables that is fine - each one already spreads across the whole cluster,
so overlapping them wins little. It is the opposite for the common case of many
small tables: each table's Spark job leaves most of the cluster idle while the
driver waits for it, and total runtime becomes the sum of a lot of mostly-idle
waits. Submitting several tables' jobs concurrently from the driver lets Spark's
scheduler pack them together.

Three things make this safe rather than merely faster:

1. **Cancellation keeps working.** The Glue job stops a run with
   ``cancelJobGroup(job_id)``, and a Spark job group is *thread-local* - work
   submitted from a worker thread would not carry it, so a user's Cancel would
   silently do nothing while the job kept burning cluster time. Each worker
   re-applies the driver's job group before doing anything.

2. **Concurrency is bounded.** Every in-flight table caches a DataFrame, so
   unbounded workers means unbounded driver and executor memory. The cap is
   deliberately small and configurable.

3. **A failure is per-table.** One table raising must not lose the results of
   the tables that already succeeded, so exceptions are captured against their
   table and returned, not propagated out of the pool.
"""

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


# Small on purpose. Each concurrent table holds a cached DataFrame, and the
# driver coordinates all of them; the aim is to stop the cluster idling between
# tables, not to run everything at once. Override per deployment with
# DQ_MAX_TABLE_WORKERS, or per job with config["max_table_workers"].
DEFAULT_MAX_TABLE_WORKERS = 4

_JOB_GROUP_ID = "spark.jobGroup.id"
_JOB_DESCRIPTION = "spark.job.description"


@dataclass
class TaskOutcome:
    """One item's result, or the exception it raised. Never both."""

    index: int
    item: Any
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def resolve_max_workers(config: Any = None) -> int:
    """Return the configured table-level concurrency, floored at 1.

    Order of precedence: the job's own config, then the environment, then the
    default. A value of 1 restores the original strictly-sequential behaviour,
    which is the escape hatch if a deployment ever needs it.
    """
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
    """Read the driver thread's Spark job group, if a session exists."""
    try:
        from engine.core.spark_session import get_spark_session

        context = get_spark_session().sparkContext
        return (
            context.getLocalProperty(_JOB_GROUP_ID),
            context.getLocalProperty(_JOB_DESCRIPTION),
        )
    except Exception:
        # No session yet, or a Spark build without local properties. Parallelism
        # still works; only group-based cancellation would be unavailable, and
        # that is what the warning in run_in_parallel covers.
        logger.debug("Could not read the current Spark job group", exc_info=True)
        return None, None


def _apply_job_group(group_id: str | None, description: str | None) -> None:
    """Re-apply the driver's job group inside a worker thread."""
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
    """Run ``worker`` over ``items`` with bounded concurrency.

    Returns one TaskOutcome per item, in the input's order regardless of the
    order they finished, so downstream results stay deterministic.

    Runs inline - no pool, no threads - for a single item or a worker count of
    one, so the common small job behaves exactly as it did before.
    """
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
        # The worker runs on a pool thread, which does not inherit the driver
        # thread's job group - without this, cancelJobGroup() would not reach
        # anything submitted here.
        _apply_job_group(group_id, group_description)

        if cancel_event is not None and cancel_event.is_set():
            return TaskOutcome(index=index, item=item, error=_cancelled())

        try:
            return TaskOutcome(index=index, item=item, value=worker(item))
        except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised by the caller if it wants
            return TaskOutcome(index=index, item=item, error=exc)

    logger.info(
        "Running %s %s(s) with up to %s workers",
        len(items),
        description,
        workers,
    )

    # inheritable_thread_target also ensures the JVM-side thread is closed when
    # the Python thread finishes, which matters for a long Glue run that would
    # otherwise accumulate JVM threads.
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
    """The single-worker path: identical semantics, without touching threads."""
    outcomes: list[TaskOutcome] = []

    for index, item in enumerate(items):
        if cancel_event is not None and cancel_event.is_set():
            outcomes.append(TaskOutcome(index=index, item=item, error=_cancelled()))
            continue

        try:
            outcomes.append(TaskOutcome(index=index, item=item, value=worker(item)))
        except BaseException as exc:  # noqa: BLE001
            outcomes.append(TaskOutcome(index=index, item=item, error=exc))

    return outcomes


def _cancelled() -> BaseException:
    from utils.job_cancellation import JobCancelledError

    return JobCancelledError("Job cancelled by user")
