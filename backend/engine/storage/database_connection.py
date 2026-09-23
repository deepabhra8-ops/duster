from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseConnection:
    def __init__(
        self,
        config: Mapping[str, Any],
    ) -> None:
        try:
            self.config = config
            self._engine: Engine | None = None
            logger.debug("Initialized database connection")
        except Exception:
            logger.exception("Failed to initialize database connection")
            raise

    def connect(self) -> Engine:
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
        try:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
                logger.debug("Closed database engine")
        except Exception:
            logger.exception("Failed to close database engine")
            raise

    def dispose(self) -> None:
        self.close()

    @property
    def connection_string(self) -> str:
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
        return self._engine is not None

    @property
    def engine(self) -> Engine:
        return self.connect()

    def execute(
        self,
        operation,
    ):
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
        return self.connect().begin()

    def connect_context(self):
        return self.connect().connect()

    def __enter__(self) -> "DatabaseConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()
