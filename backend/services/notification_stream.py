from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from starlette.concurrency import run_in_threadpool

from repositories.notification_repository import NotificationRepository, notification_repository
from services.auth_service import auth_service
from utils.logger import get_logger


logger = get_logger(__name__)


HEARTBEAT_SECONDS = 20.0

RETRY_MILLISECONDS = 5000


def format_event(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    lines = []

    if event_id is not None:
        lines.append(f"id: {event_id}")

    lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, separators=(",", ":")))

    return "\n".join(lines) + "\n\n"


async def notification_event_stream(
    username: str,
    session_id: str | None,
    *,
    after_id: int,
    poll_seconds: float,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    repository: NotificationRepository | None = None,
    session_check: Callable[[str | None], str | None] | None = None,
) -> AsyncIterator[str]:
    repository = repository or notification_repository
    session_check = session_check or auth_service.peek_current_user

    cursor = after_id
    yield f"retry: {RETRY_MILLISECONDS}\n\n"

    clock = time.monotonic
    last_sent = last_session_check = clock()

    while True:
        await asyncio.sleep(poll_seconds)

        try:
            rows = await run_in_threadpool(repository.list_since, username, cursor)

            if rows:
                unread = await run_in_threadpool(repository.unread_count, username)

                for row in rows:
                    yield format_event(
                        "notification",
                        {"notification": row, "unread_count": unread},
                        event_id=row["id"],
                    )

                cursor = rows[-1]["id"]
                last_sent = clock()
        except Exception:
            logger.warning(
                "Notification stream poll failed for '%s'; will retry", username, exc_info=True
            )

        if clock() - last_session_check >= heartbeat_seconds:
            last_session_check = clock()

            if await run_in_threadpool(session_check, session_id) != username:
                logger.info("Ending notification stream for '%s': session is no longer valid", username)
                return

        if clock() - last_sent >= heartbeat_seconds:
            last_sent = clock()
            yield ": ping\n\n"
