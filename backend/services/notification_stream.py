"""Server-Sent Events feed of a user's new notifications.

Why this polls the database instead of being pushed to. Notifications are written
by processes this one cannot observe: above all the Glue run, which writes job
results to Postgres directly, and the API runs several worker processes, so a
notification created in one is not in another's memory. LISTEN/NOTIFY would be the
usual answer, but the app talks to Postgres through pgbouncer with unpooled
connections, which cannot hold a LISTEN. So each open stream asks a small indexed
question every few seconds - "anything for me newer than the last id I sent?" -
and that works no matter which process wrote the row.

Why SSE and not a WebSocket: the traffic is one-way, EventSource reconnects by
itself, and it is plain HTTP, so it goes through the existing session cookie, CORS
and Nginx proxy without a second protocol to secure.
"""

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


# Quiet streams send a comment this often. It keeps Nginx (proxy_read_timeout 120s)
# and the load balancer's idle timeout (60s by default) from closing a connection
# that is healthy but has nothing to say, and it is also when the session is
# re-checked.
HEARTBEAT_SECONDS = 20.0

# How long the browser waits before reconnecting after the server drops the stream.
RETRY_MILLISECONDS = 5000


def format_event(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    """Encode one SSE message. json.dumps never emits a raw newline, so `data:` is a single line."""
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
    """Yield SSE frames for `username`'s notifications newer than `after_id`.

    Runs until the client disconnects (the response task is cancelled, which lands
    on the `await` below) or the session ends. Each event carries the user's unread
    count as well as the notification, so a badge that has drifted - say, from
    marking things read in another tab - corrects itself on the next arrival.

    The blocking database calls run in a worker thread; this is async so that one
    open stream costs a coroutine and not a thread.
    """
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
            # A database blip must not end the stream and make every open tab
            # reconnect at once. The next tick asks again from the same cursor.
            logger.warning(
                "Notification stream poll failed for '%s'; will retry", username, exc_info=True
            )

        if clock() - last_session_check >= heartbeat_seconds:
            last_session_check = clock()

            # Ends the stream once the user signs out or the session expires. The
            # browser reconnects, is refused with a 401, and the app returns to the
            # login page - rather than this stream quietly outliving the session.
            if await run_in_threadpool(session_check, session_id) != username:
                logger.info("Ending notification stream for '%s': session is no longer valid", username)
                return

        if clock() - last_sent >= heartbeat_seconds:
            last_sent = clock()
            yield ": ping\n\n"
