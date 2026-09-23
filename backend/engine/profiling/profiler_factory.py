"""Builds a profiler instance for a source type, wiring in the dependencies its data source exposes."""

from __future__ import annotations

from typing import Any

from engine.core.execution_context import ExecutionContext
from engine.data_sources.base_data_source import BaseDataSource
from engine.profiling.base_profiler import BaseProfiler
from engine.profiling.profiler_registry import (
    ProfilerRegistry,
    default_profiler_registry,
)
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfilerFactory:
    """Creates profiler instances, supplying dependencies from the data source being profiled."""

    def __init__(
        self,
        registry: ProfilerRegistry | None = None,
    ) -> None:
        """Store the profiler registry to create instances from."""
        try:
            self.registry = (
                registry
                or default_profiler_registry
            )
            logger.debug("Initialized profiler factory")
        except Exception:
            logger.exception("Failed to initialize profiler factory")
            raise

    def create(
        self,
        profiler_type: str,
        context: ExecutionContext,
        source: BaseDataSource,
    ) -> BaseProfiler:
        """Create a profiler for a source type, passing through the source's declared dependencies."""
        try:
            dependencies: dict[str, Any] = dict(
                source.profiler_dependencies()
            )

            profiler = self.registry.get(
                profiler_type=profiler_type,
                context=context,
                **dependencies,
            )
            logger.info(
                "Created profiler of type '%s'",
                profiler_type,
            )
            return profiler
        except Exception:
            logger.exception(
                "Failed to create profiler of type '%s'",
                profiler_type,
            )
            raise
