from __future__ import annotations

from threading import RLock
from typing import Type

from engine.core.execution_context import ExecutionContext
from engine.staging.base_staging_writer import BaseStagingWriter
from utils.logger import get_logger


logger = get_logger(__name__)


class StagingWriterRegistry:
    def __init__(self) -> None:
        self._writers: dict[str, Type[BaseStagingWriter]] = {}
        self._lock = RLock()

    def register(
        self,
        writer_class: Type[BaseStagingWriter],
    ) -> Type[BaseStagingWriter]:
        try:
            staging_type = self._get_staging_type(
                writer_class
            )

            with self._lock:
                if staging_type in self._writers:
                    raise ValueError(
                        f"Staging writer '{staging_type}' "
                        "is already registered."
                    )

                self._writers[staging_type] = writer_class

            logger.info(
                "Registered staging writer '%s' for type '%s'",
                writer_class.__name__,
                staging_type,
            )
            return writer_class
        except Exception:
            logger.exception(
                "Failed to register staging writer '%s'",
                getattr(writer_class, "__name__", type(writer_class).__name__),
            )
            raise

    def unregister(
        self,
        staging_type: str,
    ) -> None:
        try:
            normalized_type = self._normalize_staging_type(
                staging_type
            )

            with self._lock:
                removed = self._writers.pop(
                    normalized_type,
                    None,
                )

            logger.info(
                "Unregistered staging writer type '%s' (found=%s)",
                normalized_type,
                removed is not None,
            )
        except Exception:
            logger.exception(
                "Failed to unregister staging writer type '%s'",
                staging_type,
            )
            raise

    def get(
        self,
        staging_type: str,
        context: ExecutionContext,
    ) -> BaseStagingWriter:
        try:
            normalized_type = self._normalize_staging_type(
                staging_type
            )

            with self._lock:
                writer_class = self._writers.get(
                    normalized_type
                )

            if writer_class is None:
                raise KeyError(
                    f"No staging writer registered for type "
                    f"'{staging_type}'."
                )

            writer = writer_class(
                context=context,
            )
            logger.debug(
                "Created staging writer '%s' for type '%s'",
                writer_class.__name__,
                normalized_type,
            )
            return writer
        except Exception:
            logger.exception(
                "Failed to create staging writer for type '%s'",
                staging_type,
            )
            raise

    def contains(
        self,
        staging_type: str,
    ) -> bool:
        try:
            normalized_type = self._normalize_staging_type(
                staging_type
            )

            with self._lock:
                result = normalized_type in self._writers

            logger.debug(
                "Checked staging writer type '%s': %s",
                normalized_type,
                result,
            )
            return result
        except Exception:
            logger.exception(
                "Failed to check staging writer type '%s'",
                staging_type,
            )
            raise

    def all(self) -> dict[str, Type[BaseStagingWriter]]:
        try:
            with self._lock:
                writers = dict(self._writers)

            logger.debug(
                "Retrieved %s registered staging writers",
                len(writers),
            )
            return writers
        except Exception:
            logger.exception(
                "Failed to retrieve registered staging writers"
            )
            raise

    def staging_types(self) -> list[str]:
        try:
            with self._lock:
                staging_types = list(self._writers.keys())

            logger.debug(
                "Retrieved registered staging types: %s",
                staging_types,
            )
            return staging_types
        except Exception:
            logger.exception(
                "Failed to retrieve registered staging types"
            )
            raise

    def clear(self) -> None:
        try:
            with self._lock:
                count = len(self._writers)
                self._writers.clear()

            logger.info(
                "Cleared %s registered staging writers",
                count,
            )
        except Exception:
            logger.exception(
                "Failed to clear registered staging writers"
            )
            raise

    @staticmethod
    def _get_staging_type(
        writer_class: Type[BaseStagingWriter],
    ) -> str:
        staging_type = getattr(
            writer_class,
            "staging_type",
            "",
        )

        if (
            not isinstance(staging_type, str)
            or not staging_type.strip()
        ):
            raise ValueError(
                f"Staging writer class "
                f"'{writer_class.__name__}' must define "
                "a non-empty 'staging_type'."
            )

        return StagingWriterRegistry._normalize_staging_type(
            staging_type
        )

    @staticmethod
    def _normalize_staging_type(
        staging_type: str,
    ) -> str:
        if not isinstance(staging_type, str):
            raise TypeError(
                "staging_type must be a string."
            )

        return staging_type.strip().lower()

    def register_instance(
        self,
        writer: BaseStagingWriter,
    ) -> BaseStagingWriter:
        try:
            self.register(type(writer))
            logger.debug(
                "Registered staging writer instance '%s'",
                type(writer).__name__,
            )
            return writer
        except Exception:
            logger.exception(
                "Failed to register staging writer instance '%s'",
                type(writer).__name__,
            )
            raise


default_staging_writer_registry = StagingWriterRegistry()


def register_staging_writer(
    writer_class: Type[BaseStagingWriter],
) -> Type[BaseStagingWriter]:
    return default_staging_writer_registry.register(
        writer_class
    )
