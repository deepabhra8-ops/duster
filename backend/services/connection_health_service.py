from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from core.config import (
    CONNECTION_HEARTBEAT_INTERVAL_SECONDS,
    CONNECTION_ROTATION_REMINDER_DAYS,
)
from repositories.notification_repository import NotificationRepository, notification_repository
from repositories.saved_connection_repository import (
    SavedConnectionRepository,
    saved_connection_repository,
)
from services.connectors import connector_registry
from services.metadata_scan_service import metadata_scan_service
from utils.logger import get_logger, new_request_id, set_request_id


logger = get_logger(__name__)


INITIAL_DELAY_SECONDS = 60

ROTATION_REMINDER_THROTTLE_DAYS = 7


class ConnectionHeartbeatSweep:
    def __init__(
        self,
        connections: SavedConnectionRepository | None = None,
        notifications: NotificationRepository | None = None,
        interval_seconds: int = CONNECTION_HEARTBEAT_INTERVAL_SECONDS,
        rotation_reminder_days: int = CONNECTION_ROTATION_REMINDER_DAYS,
        clock: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self.connections = connections or saved_connection_repository
        self.notifications = notifications or notification_repository
        self.interval_seconds = interval_seconds
        self.rotation_reminder_days = rotation_reminder_days
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.interval_seconds > 0

    def start(self) -> None:
        if not self.enabled:
            logger.info(
                "Connection heartbeat sweep disabled "
                "(CONNECTION_HEARTBEAT_INTERVAL_SECONDS=%s)",
                self.interval_seconds,
            )
            return

        if self._thread is not None:
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="connection-heartbeat",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Connection heartbeat sweep started: saved connections are re-tested "
            "every %ss and rotation reminders fire after %s day(s)",
            self.interval_seconds,
            self.rotation_reminder_days,
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
                logger.exception("Connection heartbeat sweep failed")

            self._stop.wait(self.interval_seconds)

    def sweep(self) -> int:
        set_request_id(f"heartbeat-{new_request_id()[:8]}")

        checked = 0

        for summary in self.connections.list_all():
            try:
                self.check_connection(summary)
                checked += 1
            except Exception:
                logger.exception("Heartbeat failed for connection '%s'", summary.get("id"))

        return checked

    def check_connection(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        connection_id = summary["id"]
        decrypted = self.connections.get_decrypted(connection_id)

        if decrypted is None:
            return None

        db_type = decrypted["db_type"]
        connector = connector_registry.get(db_type)

        if connector is None:
            return None

        result = connector.heartbeat(decrypted["connection_details"])
        ok = bool(result.get("ok"))
        status = "healthy" if ok else "error"
        error = None if ok else result.get("error")

        schema_count: int | None = None
        table_count: int | None = None

        if ok:
            schema_count, table_count = self._count_metadata(
                db_type, decrypted["connection_details"]
            )

        previous_status = summary.get("last_test_status") or "unknown"

        updated = self.connections.update_health(
            connection_id=connection_id,
            status=status,
            error=error,
            tested_at=self._clock(),
            schema_count=schema_count,
            table_count=table_count,
        )

        if previous_status == "healthy" and status == "error":
            self._notify_owner(
                summary,
                title="Connection lost",
                content=(
                    f"'{summary.get('name')}' stopped responding to health checks: "
                    f"{error or 'connection failed'}."
                ),
            )

        self._maybe_remind_rotation(summary)

        return updated

    def _count_metadata(
        self,
        db_type: str,
        connection_details: dict[str, Any],
    ) -> tuple[int | None, int | None]:
        try:
            schemas = metadata_scan_service.list_schemas(db_type, connection_details)
        except Exception:
            return None, None

        table_total = 0

        for schema in schemas:
            try:
                table_total += len(
                    metadata_scan_service.list_tables(db_type, connection_details, schema)
                )
            except Exception:
                continue

        return len(schemas), table_total

    def _maybe_remind_rotation(self, summary: dict[str, Any]) -> None:
        last_rotated_at = summary.get("last_rotated_at") or summary.get("created_at")

        if last_rotated_at is None:
            return

        now = self._clock()

        if now - last_rotated_at < timedelta(days=self.rotation_reminder_days):
            return

        last_reminded = summary.get("rotation_reminded_at")

        if last_reminded and now - last_reminded < timedelta(
            days=ROTATION_REMINDER_THROTTLE_DAYS
        ):
            return

        self._notify_owner(
            summary,
            title="Connection credentials due for rotation",
            content=(
                f"'{summary.get('name')}' credentials haven't been rotated in over "
                f"{self.rotation_reminder_days} day(s). Consider updating them."
            ),
        )
        self.connections.mark_rotation_reminded(summary["id"], now)

    def _notify_owner(self, summary: dict[str, Any], title: str, content: str) -> None:
        owner = summary.get("created_by")

        if not owner:
            return

        try:
            self.notifications.create(
                username=owner,
                type_="connection_health",
                title=title,
                content=content,
                link="/connections",
            )
        except Exception:
            logger.exception(
                "Failed to notify '%s' about connection '%s'", owner, summary.get("id")
            )


connection_heartbeat_sweep = ConnectionHeartbeatSweep()


def run_heartbeat(connection_id: str) -> dict[str, Any] | None:
    summary = saved_connection_repository.get(connection_id)

    if summary is None:
        return None

    return connection_heartbeat_sweep.check_connection(summary)
