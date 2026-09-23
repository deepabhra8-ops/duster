"""Registry mapping a source type string to its registered BaseDataSource class."""

from __future__ import annotations

from threading import RLock
from typing import Type

from engine.core.execution_context import ExecutionContext
from engine.data_sources.base_data_source import BaseDataSource
from utils.logger import get_logger, log_and_reraise


logger = get_logger(__name__)


class SourceRegistry:
    """Thread-safe registry of BaseDataSource classes keyed by source type."""

    def __init__(self) -> None:
        self._sources: dict[str, Type[BaseDataSource]] = {}
        self._lock = RLock()

    @log_and_reraise(logger, "Failed to register data source")
    def register(
        self,
        source_class: Type[BaseDataSource],
    ) -> Type[BaseDataSource]:
        """Register a data source class under its source_type."""
        source_type = self._get_source_type(source_class)

        with self._lock:
            if source_type in self._sources:
                raise ValueError(
                    f"Data source '{source_type}' is already registered."
                )

            self._sources[source_type] = source_class

        logger.info(
            "Registered data source '%s' for type '%s'",
            source_class.__name__,
            source_type,
        )
        return source_class

    @log_and_reraise(
        logger,
        lambda self, source_type, **_: (
            "Failed to unregister data source '%s'",
            source_type,
        ),
    )
    def unregister(
        self,
        source_type: str,
    ) -> None:
        """Remove a registered data source type."""
        normalized_type = self._normalize_source_type(source_type)

        with self._lock:
            removed = self._sources.pop(normalized_type, None)

        logger.info(
            "Unregistered data source type '%s' (found=%s)",
            normalized_type,
            removed is not None,
        )

    @log_and_reraise(
        logger,
        lambda self, source_type, **_: (
            "Failed to create data source '%s'",
            source_type,
        ),
    )
    def get(
        self,
        source_type: str,
        config: dict,
        context: ExecutionContext,
    ) -> BaseDataSource:
        """Instantiate the registered data source for a source type."""
        normalized_type = self._normalize_source_type(source_type)

        with self._lock:
            source_class = self._sources.get(normalized_type)

        if source_class is None:
            raise KeyError(
                f"No data source registered for type '{source_type}'."
            )

        source = source_class(
            config=config,
            context=context,
        )
        logger.debug("Created data source '%s'", normalized_type)
        return source

    @log_and_reraise(
        logger,
        lambda self, source_type, **_: (
            "Failed to check data source '%s'",
            source_type,
        ),
    )
    def contains(
        self,
        source_type: str,
    ) -> bool:
        """Return whether a source type is registered."""
        normalized_type = self._normalize_source_type(source_type)

        with self._lock:
            result = normalized_type in self._sources

        logger.debug("Checked data source type '%s': %s", normalized_type, result)
        return result

    def all(self) -> dict[str, Type[BaseDataSource]]:
        """Return all registered source classes keyed by source type."""
        with self._lock:
            return dict(self._sources)

    def source_types(self) -> list[str]:
        """Return all registered source type names."""
        with self._lock:
            return list(self._sources.keys())

    @log_and_reraise(logger, "Failed to clear registered data sources")
    def clear(self) -> None:
        """Remove all registered data sources."""
        with self._lock:
            count = len(self._sources)
            self._sources.clear()
        logger.info("Cleared %s registered data sources", count)

    @staticmethod
    def _get_source_type(
        source_class: Type[BaseDataSource],
    ) -> str:
        """Return a source class's normalized source_type, or raise if it's missing."""
        source_type = getattr(
            source_class,
            "source_type",
            "",
        )

        if not isinstance(source_type, str) or not source_type.strip():
            raise ValueError(
                f"Data source class '{source_class.__name__}' "
                "must define a non-empty 'source_type'."
            )

        return SourceRegistry._normalize_source_type(source_type)

    @staticmethod
    def _normalize_source_type(
        source_type: str,
    ) -> str:
        """Normalize a source type string for lookup."""
        if not isinstance(source_type, str):
            raise TypeError(
                "source_type must be a string."
            )

        return source_type.strip().lower()

    @log_and_reraise(logger, "Failed to register data source instance")
    def register_instance(
        self,
        source: BaseDataSource,
    ) -> BaseDataSource:
        """Register the class of an already-created data source instance."""
        self.register(type(source))
        logger.debug(
            "Registered data source instance '%s'",
            type(source).__name__,
        )
        return source


default_source_registry = SourceRegistry()


def register_source(
    source_class: Type[BaseDataSource],
) -> Type[BaseDataSource]:
    """Class-decorator that registers a data source with the default registry."""
    return default_source_registry.register(source_class)
