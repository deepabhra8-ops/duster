"""Lazily creates and manages a SQLAlchemy engine from a pipeline configuration's connection string."""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseConnection:
    """Wraps a lazily created SQLAlchemy engine, resolved from a config's connection string."""

    def __init__(
        self,
        config: Mapping[str, Any],
    ) -> None:
        """Store the config; the engine is created on first connect()."""
        try:
            self.config = config
            self._engine: Engine | None = None
            logger.debug("Initialized database connection")
        except Exception:
            logger.exception("Failed to initialize database connection")
            raise

    def connect(self) -> Engine:
        """Return the SQLAlchemy engine, creating it on first use."""
        try:
            if self._engine is None:
                self._engine = create_engine(
                    self.connection_string,
                )
                logger.info("Created database engine")

            return self._engine
        except Exception:
            logger.exception("Failed to create database engine")
            raise

    def close(self) -> None:
        """Dispose the engine, if one was created."""
        try:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
                logger.debug("Closed database engine")
        except Exception:
            logger.exception("Failed to close database engine")
            raise

    def dispose(self) -> None:
        """Alias for close()."""
        self.close()

    @property
    def connection_string(self) -> str:
        """Return the configured connection string."""
        try:
            database_config = self.config.get(
                "db",
                {},
            )

            connection_string = database_config.get(
                "connection_string",
                "",
            )

            if not connection_string:
                connection_string = self.config.get(
                    "connection_string",
                    "",
                )

            connection_string = str(
                connection_string
            ).strip()

            if not connection_string:
                raise ValueError(
                    "Database connection_string is required."
                )

            return connection_string
        except Exception:
            logger.exception("Failed to resolve database connection string")
            raise

    @property
    def is_connected(self) -> bool:
        """Return whether an engine has already been created."""
        return self._engine is not None

    @property
    def engine(self) -> Engine:
        """Return the engine, creating it on first use."""
        return self.connect()

    def execute(
        self,
        operation,
    ):
        """Run a callable within a transaction and return its result."""
        try:
            engine = self.connect()

            with engine.begin() as connection:
                result = operation(connection)
            logger.debug("Executed database operation")
            return result
        except Exception:
            logger.exception("Failed to execute database operation")
            raise

    def begin(self):
        """Start a new transaction on the engine."""
        return self.connect().begin()

    def connect_context(self):
        """Return a raw connection context manager from the engine."""
        return self.connect().connect()

    def __enter__(self) -> "DatabaseConnection":
        """Connect on entering the context manager."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        """Close the engine on exiting the context manager."""
        self.close()
