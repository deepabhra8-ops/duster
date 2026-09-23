from __future__ import annotations

import re
from typing import Any

from repositories.notification_repository import (
    NotificationRepository,
    notification_repository,
)
from repositories.user_repository import user_repository
from utils.logger import get_logger


logger = get_logger(__name__)


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50

MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 1000
MAX_LINK_LENGTH = 500

_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class NotificationValidationError(ValueError):
    pass


class NotificationPermissionError(Exception):
    pass


def is_internal_link(link: str) -> bool:
    return (
        link.startswith("/")
        and not link.startswith("//")
        and "\\" not in link
        and not any(ord(char) < 32 or ord(char) == 127 for char in link)
    )


def _clean_text(value: Any, field: str, max_length: int, required: bool) -> str:
    if value is None:
        value = ""

    if not isinstance(value, str):
        raise NotificationValidationError(f"{field} must be a string")

    value = value.strip()

    if required and not value:
        raise NotificationValidationError(f"{field} is required")

    if len(value) > max_length:
        raise NotificationValidationError(f"{field} must be at most {max_length} characters")

    return value


class NotificationService:
    def __init__(self, repository: NotificationRepository | None = None) -> None:
        self.repository = repository or notification_repository

    def list_for(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_SIZE,
        before: int | None = None,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))

        items, next_cursor = self.repository.list_page(username, limit, before, unread_only)

        return {
            "items": items,
            "unread_count": self.repository.unread_count(username),
            "next_cursor": next_cursor,
        }

    def create(
        self,
        requester: str,
        *,
        type: Any,
        title: Any,
        content: Any = "",
        link: Any = None,
        username: Any = None,
    ) -> dict[str, Any]:
        if not isinstance(type, str) or not _TYPE_PATTERN.match(type):
            raise NotificationValidationError(
                "type must be a lowercase slug of letters, digits and underscores"
            )

        title = _clean_text(title, "title", MAX_TITLE_LENGTH, required=True)
        content = _clean_text(content, "content", MAX_CONTENT_LENGTH, required=False)

        if link is not None:
            link = _clean_text(link, "link", MAX_LINK_LENGTH, required=False) or None

        if link is not None and not is_internal_link(link):
            raise NotificationValidationError("link must be a path within the app, such as /validator/abc")

        target = _clean_text(username, "username", 255, required=False) or requester

        if target != requester and not user_repository.is_admin(requester):
            logger.warning(
                "User '%s' tried to create a notification for '%s'", requester, target
            )
            raise NotificationPermissionError(
                "Only an administrator can create notifications for other users"
            )

        return self.repository.create(target, type, title, content, link)

    def mark_read(self, username: str, notification_id: int) -> dict[str, Any] | None:
        notification = self.repository.mark_read(username, notification_id)

        if notification is None:
            return None

        return {
            "notification": notification,
            "unread_count": self.repository.unread_count(username),
        }

    def mark_all_read(self, username: str) -> dict[str, Any]:
        updated = self.repository.mark_all_read(username)

        return {
            "updated": updated,
            "unread_count": self.repository.unread_count(username),
        }

    def clear_all(self, username: str) -> dict[str, Any]:
        deleted = self.repository.delete_all(username)

        logger.info("Cleared %s notification(s) for '%s'", deleted, username)

        return {
            "deleted": deleted,
            "unread_count": self.repository.unread_count(username),
        }


notification_service = NotificationService()
