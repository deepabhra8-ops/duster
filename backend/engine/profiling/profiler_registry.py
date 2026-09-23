from __future__ import annotations

from threading import RLock
from typing import Any, Type

from engine.core.execution_context import ExecutionContext
from engine.profiling.base_profiler import BaseProfiler
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfilerRegistry:
    def __init__(self) -> None:
        self._profilers: dict[str, Type[BaseProfiler]] = {}
        self._lock = RLock()

    def register(
        self,
        profiler_class: Type[BaseProfiler],
    ) -> Type[BaseProfiler]:
        try:
            profiler_type = self._get_profiler_type(
                profiler_class
            )

            with self._lock:
                if profiler_type in self._profilers:
                    raise ValueError(
                        f"Profiler '{profiler_type}' is already registered."
                    )

                self._profilers[profiler_type] = profiler_class

            logger.info(
                "Registered profiler '%s' for type '%s'",
                profiler_class.__name__,
                profiler_type,
            )
            return profiler_class
        except Exception:
            logger.exception("Failed to register profiler")
            raise

    def unregister(
        self,
        profiler_type: str,
    ) -> None:
        try:
            normalized_type = self._normalize_profiler_type(
                profiler_type
            )

            with self._lock:
                removed = self._profilers.pop(
                    normalized_type,
                    None,
                )

            logger.info(
                "Unregistered profiler type '%s' (found=%s)",
                normalized_type,
                removed is not None,
            )
        except Exception:
            logger.exception("Failed to unregister profiler '%s'", profiler_type)
            raise

    def get(
        self,
        profiler_type: str,
        context: ExecutionContext,
        **dependencies: Any,
    ) -> BaseProfiler:
        try:
            normalized_type = self._normalize_profiler_type(
                profiler_type
            )

            with self._lock:
                profiler_class = self._profilers.get(
                    normalized_type
                )

            if profiler_class is None:
                raise KeyError(
                    f"No profiler registered for type "
                    f"'{profiler_type}'."
                )

            profiler = profiler_class(
                context=context,
                **dependencies,
            )
            logger.debug("Created profiler of type '%s'", normalized_type)
            return profiler
        except Exception:
            logger.exception("Failed to create profiler '%s'", profiler_type)
            raise

    def contains(
        self,
        profiler_type: str,
    ) -> bool:
        try:
            normalized_type = self._normalize_profiler_type(
                profiler_type
            )

            with self._lock:
                result = normalized_type in self._profilers

            logger.debug("Checked profiler type '%s': %s", normalized_type, result)
            return result
        except Exception:
            logger.exception("Failed to check profiler '%s'", profiler_type)
            raise

    def all(
        self,
    ) -> dict[str, Type[BaseProfiler]]:
        try:
            with self._lock:
                profilers = dict(self._profilers)
            logger.debug("Retrieved %s registered profilers", len(profilers))
            return profilers
        except Exception:
            logger.exception("Failed to retrieve registered profilers")
            raise

    def profiler_types(
        self,
    ) -> list[str]:
        try:
            with self._lock:
                profiler_types = list(self._profilers.keys())
            logger.debug("Retrieved registered profiler types: %s", profiler_types)
            return profiler_types
        except Exception:
            logger.exception("Failed to retrieve registered profiler types")
            raise

    def clear(self) -> None:
        try:
            with self._lock:
                count = len(self._profilers)
                self._profilers.clear()
            logger.info("Cleared %s registered profilers", count)
        except Exception:
            logger.exception("Failed to clear registered profilers")
            raise

    @staticmethod
    def _get_profiler_type(
        profiler_class: Type[BaseProfiler],
    ) -> str:
        profiler_type = getattr(
            profiler_class,
            "profiler_type",
            "",
        )

        if (
            not isinstance(profiler_type, str)
            or not profiler_type.strip()
        ):
            raise ValueError(
                f"Profiler class '{profiler_class.__name__}' "
                "must define a non-empty 'profiler_type'."
            )

        return ProfilerRegistry._normalize_profiler_type(
            profiler_type
        )

    @staticmethod
    def _normalize_profiler_type(
        profiler_type: str,
    ) -> str:
        if not isinstance(profiler_type, str):
            raise TypeError(
                "profiler_type must be a string."
            )

        return profiler_type.strip().lower()

    def register_instance(
        self,
        profiler: BaseProfiler,
    ) -> BaseProfiler:
        try:
            self.register(type(profiler))
            logger.debug(
                "Registered profiler instance '%s'",
                type(profiler).__name__,
            )
            return profiler
        except Exception:
            logger.exception("Failed to register profiler instance")
            raise


default_profiler_registry = ProfilerRegistry()


def register_profiler(
    profiler_class: Type[BaseProfiler],
) -> Type[BaseProfiler]:
    return default_profiler_registry.register(
        profiler_class
    )
