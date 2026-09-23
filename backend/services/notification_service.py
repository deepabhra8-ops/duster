"""Business rules for in-app notifications: validation, ownership, and who may notify whom.

Two kinds of notification exist. Job-finished ones are written by a trigger on
`jobs` (migration 008), because the Glue run - which finishes almost every job -
writes to Postgres directly and never passes through this process. Everything else
is created through POST /api/notifications, which is what create() serves.
"""

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

# A short slug, e.g. job_done. Not an enum: the UI falls back to a neutral icon for
# a type it does not know, so a new type needs no migration.
_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class NotificationValidationError(ValueError):
    """The request body is not a valid notification. The message is safe to show the caller."""


class NotificationPermissionError(Exception):
    """The caller may not create a notification for someone else."""


def is_internal_link(link: str) -> bool:
    """Return True only for an in-app path such as /validator/abc.

    Clicking a notification navigates, so a link that can leave the app would let
    anything able to create a row send a user to an external site. "//host" is
    protocol-relative and a backslash is read as a slash by browsers, so both count
    as leaving. Control characters are refused too: browsers strip tabs and
    newlines from a URL, which turns "/<tab>/host" into "//host". This is stricter
    than the table's CHECK constraint, which is only a backstop.
    """
    return (
        link.startswith("/")
        and not link.startswith("//")
        and "\\" not in link
        and not any(ord(char) < 32 or ord(char) == 127 for char in link)
    )


def _clean_text(value: Any, field: str, max_length: int, required: bool) -> str:
    """Return a stripped string, or raise NotificationValidationError."""
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
    """Reads, creates and marks notifications, always on behalf of one authenticated user."""

    def __init__(self, repository: NotificationRepository | None = None) -> None:
        self.repository = repository or notification_repository

    def list_for(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_SIZE,
        before: int | None = None,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        """Return one page plus the user's total unread count.

        The count is computed over everything, not over the page: the client only
        ever holds some of the list, so counting unread rows it happens to have
        would under-report the badge as soon as there were more than a page.
        """
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
        """Create a notification, for the requester unless they are an admin naming someone else.

        The restriction is the point of this method. Without it any signed-in user
        could put a message, complete with a link, into anyone else's bell - which is
        a phishing channel that looks like it came from the product itself.
        """
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
        """Mark one of the user's notifications read. None if it is not theirs or does not exist."""
        notification = self.repository.mark_read(username, notification_id)

        if notification is None:
            return None

        return {
            "notification": notification,
            "unread_count": self.repository.unread_count(username),
        }

    def mark_all_read(self, username: str) -> dict[str, Any]:
        """Mark all of the user's notifications read."""
        updated = self.repository.mark_all_read(username)

        return {
            "updated": updated,
            "unread_count": self.repository.unread_count(username),
        }

    def clear_all(self, username: str) -> dict[str, Any]:
        """Delete all of the user's notifications, read and unread. Irreversible.

        The unread count is read back rather than assumed to be zero: a notification
        can arrive between the delete and the count.
        """
        deleted = self.repository.delete_all(username)

        logger.info("Cleared %s notification(s) for '%s'", deleted, username)

        return {
            "deleted": deleted,
            "unread_count": self.repository.unread_count(username),
        }


notification_service = NotificationService()
