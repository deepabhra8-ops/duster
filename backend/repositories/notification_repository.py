"""SQLAlchemy-backed storage for in-app notifications (the top bar's bell).

Every query is scoped by `username`. That is what stops one user reading, or
marking read, another's notifications: callers pass the authenticated username
in, and a row belonging to someone else is indistinguishable from a row that does
not exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from core.db import get_db_session
from repositories.models import Notification
from utils.logger import get_logger


logger = get_logger(__name__)


def _now_utc() -> datetime:
    """Naive UTC, matching how every other timestamp in this database is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_iso(value: datetime) -> str:
    """ISO-8601 carrying an explicit UTC offset.

    Timestamps are stored naive. Serialised bare, a browser's `new Date(...)` reads
    them as local time, so every relative label ("5 minutes ago") comes out hours
    wrong for anyone not on UTC.
    """
    return value.replace(tzinfo=timezone.utc).isoformat()


class NotificationRepository:
    """CRUD for the `notifications` table."""

    def create(
        self,
        username: str,
        type_: str,
        title: str,
        content: str = "",
        link: str | None = None,
    ) -> dict[str, Any]:
        """Insert an unread notification and return it."""
        try:
            with get_db_session() as session:
                row = Notification(
                    username=username,
                    type=type_,
                    title=title,
                    content=content,
                    link=link,
                    status="unread",
                    created_at=_now_utc(),
                )
                session.add(row)

                # Flush to get the id, and read the row back before commit: the
                # session expires everything on commit, and re-reading would cost
                # a second round trip on a connection that is not pooled.
                session.flush()
                result = self._to_dict(row)
                session.commit()

                return result
        except Exception:
            logger.exception("Failed to create a notification for '%s'", username)
            raise

    def list_page(
        self,
        username: str,
        limit: int,
        before_id: int | None = None,
        unread_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Return one page, newest first, and the cursor for the next (or None).

        Keyset-paged on `id` rather than offset-paged. The list is live: a new
        notification arriving while someone scrolls would shift every offset by one
        and repeat a row at the seam of the next page, whereas "older than id N"
        means the same thing however many rows have arrived since. Backed by
        idx_notifications_user_id.
        """
        try:
            with get_db_session() as session:
                query = session.query(Notification).filter(Notification.username == username)

                if unread_only:
                    query = query.filter(Notification.status == "unread")

                if before_id is not None:
                    query = query.filter(Notification.id < before_id)

                # One extra row tells us whether another page exists, without a
                # separate COUNT over what may be a long history.
                rows = query.order_by(Notification.id.desc()).limit(limit + 1).all()

                has_more = len(rows) > limit
                rows = rows[:limit]
                next_cursor = rows[-1].id if has_more and rows else None

                return [self._to_dict(row) for row in rows], next_cursor
        except Exception:
            logger.exception("Failed to list notifications for '%s'", username)
            raise

    def unread_count(self, username: str) -> int:
        """Return how many of this user's notifications are unread (the badge)."""
        try:
            with get_db_session() as session:
                return int(
                    session.query(func.count(Notification.id))
                    .filter(Notification.username == username, Notification.status == "unread")
                    .scalar()
                    or 0
                )
        except Exception:
            logger.exception("Failed to count unread notifications for '%s'", username)
            raise

    def mark_read(self, username: str, notification_id: int) -> dict[str, Any] | None:
        """Mark one notification read and return it, or None if it is not this user's.

        Idempotent: marking an already-read notification is not an error, so a
        double click or a retry after a dropped response is harmless.
        """
        try:
            with get_db_session() as session:
                row = (
                    session.query(Notification)
                    .filter(Notification.id == notification_id, Notification.username == username)
                    .first()
                )

                if row is None:
                    return None

                row.status = "read"
                session.flush()
                result = self._to_dict(row)
                session.commit()

                return result
        except Exception:
            logger.exception(
                "Failed to mark notification %s read for '%s'", notification_id, username
            )
            raise

    def mark_all_read(self, username: str) -> int:
        """Mark every unread notification of this user read. Returns how many changed."""
        try:
            with get_db_session() as session:
                changed = (
                    session.query(Notification)
                    .filter(Notification.username == username, Notification.status == "unread")
                    .update({Notification.status: "read"}, synchronize_session=False)
                )
                session.commit()

                return int(changed)
        except Exception:
            logger.exception("Failed to mark all notifications read for '%s'", username)
            raise

    def delete_all(self, username: str) -> int:
        """Hard-delete every notification this user has, read or not. Returns how many went.

        Scoped by username like every other query here, so it can only ever touch the
        caller's own rows. There is no soft delete and no undo. That is acceptable for
        notifications, which only announce events whose real record lives elsewhere: a
        job's own page still shows how it ended.
        """
        try:
            with get_db_session() as session:
                deleted = (
                    session.query(Notification)
                    .filter(Notification.username == username)
                    .delete(synchronize_session=False)
                )
                session.commit()

                return int(deleted)
        except Exception:
            logger.exception("Failed to clear notifications for '%s'", username)
            raise

    def purge_read_before(
        self,
        cutoff: datetime,
        batch_size: int = 1000,
        max_batches: int = 100,
    ) -> int:
        """Hard-delete READ notifications created before `cutoff`, for every user. Returns how many.

        "Read" is the `status` column. Unread notifications are never touched, however old, and the
        age is counted from creation, so one that sat unread past the cutoff goes at the next sweep
        after it is read.

        Deleted in batches, each its own short transaction, rather than one statement over however
        many rows have piled up: a long DELETE holds its row locks for its whole run and would stall
        someone marking notifications read. `FOR UPDATE SKIP LOCKED` lets several workers sweep at
        once without waiting on, or double-deleting, each other's rows - which is why no advisory
        lock is needed (those are unreliable behind pgbouncer). `max_batches` bounds one call, so a
        large backlog is worked off across sweeps instead of in one long one.
        """
        total = 0

        try:
            for _ in range(max_batches):
                with get_db_session() as session:
                    ids = [
                        row[0]
                        for row in (
                            session.query(Notification.id)
                            .filter(Notification.status == "read", Notification.created_at < cutoff)
                            .order_by(Notification.id)
                            .limit(batch_size)
                            .with_for_update(skip_locked=True)
                            .all()
                        )
                    ]

                    if not ids:
                        break

                    session.query(Notification).filter(Notification.id.in_(ids)).delete(
                        synchronize_session=False
                    )
                    session.commit()

                total += len(ids)

                # A short batch means the backlog is exhausted; don't spend another round trip
                # finding that out.
                if len(ids) < batch_size:
                    break

            return total
        except Exception:
            logger.exception(
                "Failed to purge read notifications created before %s (%s deleted before failing)",
                cutoff,
                total,
            )
            raise

    def latest_id(self, username: str) -> int:
        """Return the highest notification id this user has, or 0 if none.

        Where a live stream starts from: it pushes only what is newer than this.
        """
        try:
            with get_db_session() as session:
                return int(
                    session.query(func.max(Notification.id))
                    .filter(Notification.username == username)
                    .scalar()
                    or 0
                )
        except Exception:
            logger.exception("Failed to read the latest notification id for '%s'", username)
            raise

    def list_since(self, username: str, after_id: int, limit: int = 100) -> list[dict[str, Any]]:
        """Return notifications newer than `after_id`, oldest first - what a stream sends.

        A row's id is assigned when it is inserted but only becomes visible when its
        transaction commits, so two near-simultaneous inserts can become visible out
        of id order and a poll between them would step past the later-committed,
        lower id. The window is a few milliseconds and the cost is one missed live
        push - the row is still in the list the next time the popover is opened.
        """
        try:
            with get_db_session() as session:
                rows = (
                    session.query(Notification)
                    .filter(Notification.username == username, Notification.id > after_id)
                    .order_by(Notification.id.asc())
                    .limit(limit)
                    .all()
                )

                return [self._to_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to poll notifications for '%s'", username)
            raise

    @staticmethod
    def _to_dict(row: Notification) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "type": row.type,
            "title": row.title,
            "content": row.content or "",
            "status": row.status,
            "link": row.link,
            "created_at": _utc_iso(row.created_at),
        }


notification_repository = NotificationRepository()
