"""Registry mapping a database type string to its registered DatabaseConnector class."""

from __future__ import annotations

from threading import RLock
from typing import Type

from services.connectors.base_connector import DatabaseConnector
from utils.logger import get_logger


logger = get_logger(__name__)


class ConnectorRegistry:
    """Thread-safe registry of DatabaseConnector classes keyed by database type."""

    def __init__(self) -> None:
        self._connectors: dict[str, Type[DatabaseConnector]] = {}
        self._lock = RLock()

    def register(
        self,
        connector_class: Type[DatabaseConnector],
    ) -> Type[DatabaseConnector]:
        """Register a connector class under its db_type."""
        db_type = self._get_db_type(connector_class)

        with self._lock:
            if db_type in self._connectors:
                raise ValueError(
                    f"Database connector '{db_type}' is already registered."
                )

            self._connectors[db_type] = connector_class

        logger.info(
            "Registered database connector '%s' for type '%s'",
            connector_class.__name__,
            db_type,
        )
        return connector_class

    def get(
        self,
        db_type: str,
    ) -> DatabaseConnector | None:
        """Return a new connector instance for a database type, or None if unregistered."""
        normalized_type = self._normalize(db_type)

        with self._lock:
            connector_class = self._connectors.get(normalized_type)

        if connector_class is None:
            return None

        return connector_class()

    def contains(
        self,
        db_type: str,
    ) -> bool:
        """Return whether a database type is registered."""
        with self._lock:
            return self._normalize(db_type) in self._connectors

    def db_types(self) -> list[str]:
        """Return all registered database type names."""
        with self._lock:
            return list(self._connectors.keys())

    @staticmethod
    def _get_db_type(
        connector_class: Type[DatabaseConnector],
    ) -> str:
        """Return a connector class's normalized db_type, or raise if it's missing."""
        db_type = getattr(connector_class, "db_type", "")

        if not isinstance(db_type, str) or not db_type.strip():
            raise ValueError(
                f"Connector '{connector_class.__name__}' must define a "
                "non-empty 'db_type'."
            )

        return ConnectorRegistry._normalize(db_type)

    @staticmethod
    def _normalize(db_type: str) -> str:
        """Normalize a database type string for lookup."""
        return str(db_type).strip().lower()


default_connector_registry = ConnectorRegistry()


def register_connector(
    connector_class: Type[DatabaseConnector],
) -> Type[DatabaseConnector]:
    """Class-decorator that registers a connector with the default registry."""
    return default_connector_registry.register(connector_class)
