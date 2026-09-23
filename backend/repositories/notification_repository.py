from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from core.db import get_db_session
from repositories.models import Notification
from utils.logger import get_logger


logger = get_logger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


class NotificationRepository:
    def create(
        self,
        username: str,
        type_: str,
        title: str,
        content: str = "",
        link: str | None = None,
    ) -> dict[str, Any]:
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
        try:
            with get_db_session() as session:
                query = session.query(Notification).filter(Notification.username == username)

                if unread_only:
                    query = query.filter(Notification.status == "unread")

                if before_id is not None:
                    query = query.filter(Notification.id < before_id)

                rows = query.order_by(Notification.id.desc()).limit(limit + 1).all()

                has_more = len(rows) > limit
                rows = rows[:limit]
                next_cursor = rows[-1].id if has_more and rows else None

                return [self._to_dict(row) for row in rows], next_cursor
        except Exception:
            logger.exception("Failed to list notifications for '%s'", username)
            raise

    def unread_count(self, username: str) -> int:
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
