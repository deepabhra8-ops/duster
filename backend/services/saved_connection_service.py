from __future__ import annotations

from typing import Any

from repositories.saved_connection_repository import saved_connection_repository
from repositories.user_repository import user_repository
from services.connection_service import connection_service
from services.connectors import connector_registry
from utils.logger import get_logger


logger = get_logger(__name__)


class ConnectionPermissionError(Exception):
    pass


class SavedConnectionService:
    def list_all(self) -> list[dict[str, Any]]:
        return saved_connection_repository.list_all()

    def list_page(
        self,
        search: str = "",
        db_type: str = "",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
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
        return saved_connection_repository.get(connection_id)

    def create(
        self,
        name: str,
        db_type: str,
        connection_details: dict[str, Any],
        created_by: str,
        description: str | None = None,
    ) -> dict[str, Any]:
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
        existing = saved_connection_repository.get(connection_id)

        if existing is None:
            return False

        self._require_owner(existing, username, action="delete")
        return saved_connection_repository.delete(connection_id)

    def reveal(self, connection_id: str, username: str) -> dict[str, Any] | None:
        existing = saved_connection_repository.get(connection_id)

        if existing is None:
            return None

        self._require_owner(existing, username, action="reveal")

        logger.info(
            "User '%s' revealed credentials for connection '%s'", username, connection_id
        )
        return saved_connection_repository.get_decrypted(connection_id)

    def get_decrypted_for_run(self, connection_id: str) -> dict[str, Any] | None:
        return saved_connection_repository.get_decrypted(connection_id)

    def list_schemas(self, connection_id: str) -> list[str] | None:
        decrypted = saved_connection_repository.get_decrypted(connection_id)

        if decrypted is None:
            return None

        return self._scanner().list_schemas(
            database_type=decrypted["db_type"],
            connection_details=decrypted["connection_details"],
        )

    def list_tables(self, connection_id: str, schema: str) -> list[str] | None:
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
        from services.metadata_scan_service import metadata_scan_service

        return metadata_scan_service

    @staticmethod
    def _require_owner(
        connection: dict[str, Any],
        username: str,
        action: str,
    ) -> None:
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
