"""Validation and access control for saved database connections.

Connections are shared but owner-managed: every authenticated user may list and
use any connection, but only its creator (or an admin) may edit, delete, or
reveal its credentials. Ownership is enforced here rather than in the routes so
every caller goes through the same check.
"""

from __future__ import annotations

from typing import Any

from repositories.saved_connection_repository import saved_connection_repository
from repositories.user_repository import user_repository
from services.connection_service import connection_service
from services.connectors import connector_registry
from utils.logger import get_logger


logger = get_logger(__name__)


class ConnectionPermissionError(Exception):
    """Raised when a user tries to modify or reveal a connection they don't own.

    Routes translate this to a 403 - distinct from a missing connection (404) so
    the caller can tell "not yours" from "not there".
    """


class SavedConnectionService:
    """Validates connection details, enforces ownership, then delegates to the repository."""

    def list_all(self) -> list[dict[str, Any]]:
        """Return every saved connection's non-secret fields (shared visibility)."""
        return saved_connection_repository.list_all()

    def list_page(
        self,
        search: str = "",
        db_type: str = "",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return one page of connections, filtered and paginated in SQL.

        Mirrors JobService.list_jobs's envelope shape (total/page/pageSize/
        totalPages), for the Connections manager page.
        """
        rows, total = saved_connection_repository.list_page(
            search=search,
            db_type=db_type,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

        total_pages = (total + page_size - 1) // page_size if page_size else 1

        return {
            "data": rows,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": total_pages,
        }

    def get(self, connection_id: str) -> dict[str, Any] | None:
        """Return one connection's non-secret fields, or None if it doesn't exist."""
        return saved_connection_repository.get(connection_id)

    def create(
        self,
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
        created_by: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Validate then persist a new connection.

        Raises ValueError on invalid input (routes turn that into a 400).
        """
        name, db_type, description = self._clean(name, db_type, description)
        self._validate(name, db_type, connection_details)

        logger.info("Saving new connection '%s' (%s)", name, db_type)
        return saved_connection_repository.create(
            name=name,
            db_type=db_type,
            connection_details=connection_details or {},
            created_by=created_by,
            description=description,
        )

    def update(
        self,
        connection_id: str,
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
        username: str,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        """Validate ownership and input, then overwrite an existing connection.

        Returns None if it doesn't exist (404). Raises ConnectionPermissionError
        if `username` is neither the owner nor an admin (403), ValueError on
        invalid input (400).
        """
        existing = saved_connection_repository.get(connection_id)

        if existing is None:
            return None

        self._require_owner(existing, username, action="edit")

        name, db_type, description = self._clean(name, db_type, description)
        self._validate(name, db_type, connection_details)

        return saved_connection_repository.update(
            connection_id=connection_id,
            name=name,
            db_type=db_type,
            connection_details=connection_details or {},
            description=description,
        )

    def delete(self, connection_id: str, username: str) -> bool:
        """Delete a connection the user owns. Returns False if it doesn't exist."""
        existing = saved_connection_repository.get(connection_id)

        if existing is None:
            return False

        self._require_owner(existing, username, action="delete")
        return saved_connection_repository.delete(connection_id)

    def reveal(self, connection_id: str, username: str) -> dict[str, Any] | None:
        """Return decrypted credentials, for the owner (or an admin) only.

        This is the single path by which stored credentials leave the server, so
        it is owner-gated and logged. Other users can still *use* the connection
        - resolution at job-run time goes through get_decrypted_for_run() instead,
        which never returns the details to a browser.
        """
        existing = saved_connection_repository.get(connection_id)

        if existing is None:
            return None

        self._require_owner(existing, username, action="reveal")

        logger.info(
            "User '%s' revealed credentials for connection '%s'", username, connection_id
        )
        return saved_connection_repository.get_decrypted(connection_id)

    def get_decrypted_for_run(self, connection_id: str) -> dict[str, Any] | None:
        """Return decrypted details for server-side use when running a job.

        Not ownership-gated: connections are shared for *use*, and these details
        never reach the browser - they go into the job config consumed by Glue.
        """
        return saved_connection_repository.get_decrypted(connection_id)

    def list_schemas(self, connection_id: str) -> list[str] | None:
        """Fetch the connection's schema names live. Returns None if it is gone.

        Read from the source on demand, exactly like list_tables and list_columns
        below - schemas are no longer cached on the connection row. Saving a
        connection therefore does no catalog work at all, and a schema added to
        the source after the connection was saved shows up on the next pick
        rather than waiting for someone to press refresh. See migration 007.
        """
        decrypted = saved_connection_repository.get_decrypted(connection_id)

        if decrypted is None:
            return None

        return self._scanner().list_schemas(
            database_type=decrypted["db_type"],
            connection_details=decrypted["connection_details"],
        )

    def list_tables(self, connection_id: str, schema: str) -> list[str] | None:
        """Fetch one schema's tables live. Returns None if the connection is gone."""
        decrypted = saved_connection_repository.get_decrypted(connection_id)

        if decrypted is None:
            return None

        return self._scanner().list_tables(
            database_type=decrypted["db_type"],
            connection_details=decrypted["connection_details"],
            schema=schema,
        )

    def list_columns(
        self,
        connection_id: str,
        schema: str,
        table: str,
    ) -> list[str] | None:
        """Fetch one table's columns live. Returns None if the connection is gone."""
        decrypted = saved_connection_repository.get_decrypted(connection_id)

        if decrypted is None:
            return None

        return self._scanner().list_columns(
            database_type=decrypted["db_type"],
            connection_details=decrypted["connection_details"],
            schema=schema,
            table=table,
        )

    @staticmethod
    def _scanner():
        """Return the catalog scanner.

        Imported lazily: metadata_scan_service pulls in connection_service and the
        connector registry, and this module is imported by routes at startup -
        keeping it deferred avoids a circular import.
        """
        from services.metadata_scan_service import metadata_scan_service

        return metadata_scan_service

    @staticmethod
    def _require_owner(
        connection: dict[str, Any],
        username: str,
        action: str,
    ) -> None:
        """Raise ConnectionPermissionError unless `username` owns this connection or is an admin.

        A connection with no owner predates ownership tracking (created by an
        earlier build). Everyone can still use it, but modifying it is restricted
        to admins rather than opened to all - the alternative would be either
        inventing an owner or leaving the row permanently unmanageable.
        """
        owner = connection.get("created_by")

        if owner and owner == username:
            return

        if user_repository.is_admin(username):
            logger.info(
                "Admin '%s' performing '%s' on connection '%s' owned by '%s'",
                username,
                action,
                connection.get("id"),
                owner,
            )
            return

        raise ConnectionPermissionError(
            f"Only the user who created this connection can {action} it."
        )

    @staticmethod
    def _clean(
        name: str,
        db_type: str,
        description: str | None,
    ) -> tuple[str, str, str | None]:
        """Normalize whitespace on the free-text fields."""
        return (
            (name or "").strip(),
            (db_type or "").strip(),
            (description or "").strip() or None,
        )

    @staticmethod
    def _validate(
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
    ) -> None:
        """Raise ValueError if the name/type are missing or the details are incomplete."""
        if not name:
            raise ValueError("Name is required")

        if not db_type:
            raise ValueError("Database type is required")

        if connector_registry.get(db_type) is None:
            raise ValueError(f"Unsupported database type: {db_type}")

        missing = connection_service.validate_connection_details(
            db_type,
            connection_details or {},
        )

        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")


saved_connection_service = SavedConnectionService()
