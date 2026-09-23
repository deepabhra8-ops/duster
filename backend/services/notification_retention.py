from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from core.config import NOTIFICATION_RETENTION_DAYS
from repositories.notification_repository import NotificationRepository, notification_repository
from utils.logger import get_logger, new_request_id, set_request_id


logger = get_logger(__name__)


SWEEP_INTERVAL_SECONDS = 60 * 60

INITIAL_DELAY_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationRetention:
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
        return self.retention_days > 0

    def start(self) -> None:
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
                logger.exception("Notification retention sweep failed")

            self._stop.wait(SWEEP_INTERVAL_SECONDS)

    def cutoff(self) -> datetime:
        return self._clock() - timedelta(days=self.retention_days)

    def sweep(self) -> int:
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
