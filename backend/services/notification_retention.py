"""Deletes read notifications once they are old enough.

The rule: a notification that has been READ and was created more than
NOTIFICATION_RETENTION_DAYS ago (7 by default) is hard-deleted. Two things about it are easy
to get wrong, so they are stated here:

  * The age runs from when the notification was CREATED, not from when it was read. A
    notification that sat unread for longer than the window disappears at the next sweep after
    the user opens it. That is the requirement, and it is also why no `read_at` column exists.
  * Unread notifications are never deleted, however old. Only the `status` column decides.

It is a background sweep started from the app's lifespan: nothing outside the process is there to
schedule it, and a per-request cleanup would only ever tidy up for users who happen to log in.
Every Uvicorn worker runs one. They do not need to elect a leader - the repository deletes in
batches with FOR UPDATE SKIP LOCKED, so concurrent sweeps take different rows and the extra ones
simply find little to do.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from core.config import NOTIFICATION_RETENTION_DAYS
from repositories.notification_repository import NotificationRepository, notification_repository
from utils.logger import get_logger, new_request_id, set_request_id


logger = get_logger(__name__)


# Hourly is far finer than the granularity of a window measured in days; what it buys is that a
# restarted or newly scaled worker never leaves a backlog waiting long.
SWEEP_INTERVAL_SECONDS = 60 * 60

# Wait before the first sweep so a starting worker serves traffic before it starts deleting.
INITIAL_DELAY_SECONDS = 60


def _utc_now() -> datetime:
    """Naive UTC, matching how notifications' created_at is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationRetention:
    """Periodically deletes read notifications that have outlived the retention window."""

    def __init__(
        self,
        repository: NotificationRepository | None = None,
        retention_days: int = NOTIFICATION_RETENTION_DAYS,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.repository = repository or notification_repository
        self.retention_days = retention_days
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        """Zero or negative disables the sweep. It never means "keep nothing"."""
        return self.retention_days > 0

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin sweeping in a background thread, unless retention is disabled."""
        if not self.enabled:
            logger.info(
                "Notification retention disabled (NOTIFICATION_RETENTION_DAYS=%s)",
                self.retention_days,
            )
            return

        if self._thread is not None:
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="notification-retention",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Notification retention started: read notifications are deleted %s day(s) after "
            "creation (checked every %ss)",
            self.retention_days,
            SWEEP_INTERVAL_SECONDS,
        )

    def stop(self) -> None:
        """Ask the sweep to finish and stop."""
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        if self._stop.wait(INITIAL_DELAY_SECONDS):
            return

        while not self._stop.is_set():
            try:
                self.sweep()
            except Exception:
                # One failed sweep must not end the loop - the next may well succeed, and a
                # dead sweep is silent while notifications quietly pile up.
                logger.exception("Notification retention sweep failed")

            self._stop.wait(SWEEP_INTERVAL_SECONDS)

    # ── the sweep ────────────────────────────────────────────────────────

    def cutoff(self) -> datetime:
        """Read notifications created before this moment are due for deletion."""
        return self._clock() - timedelta(days=self.retention_days)

    def sweep(self) -> int:
        """Delete every read notification past the window. Returns how many were deleted."""
        # Checked here as well as in start(): sweep() is public, and a zero window would put the
        # cutoff at "now" - deleting every read notification there is.
        if not self.enabled:
            return 0

        set_request_id(f"retention-{new_request_id()[:8]}")

        deleted = self.repository.purge_read_before(self.cutoff())

        if deleted:
            logger.info(
                "Deleted %s read notification(s) created more than %s day(s) ago",
                deleted,
                self.retention_days,
            )

        return deleted


notification_retention = NotificationRetention()
