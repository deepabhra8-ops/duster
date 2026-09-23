"""Defines the BaseStagingWriter contract for writing passing (curated) rows to a staging destination."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseStagingWriter(ABC):
    """Base class for a writer that persists curated rows to a staging destination."""

    staging_type: str = ""

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
        """Store the execution context."""
        try:
            self.context = context
            logger.debug(
                "Initialized %s for staging type '%s'",
                type(self).__name__,
                self.staging_type,
            )
        except Exception:
            logger.exception(
                "Failed to initialize %s for staging type '%s'",
                type(self).__name__,
                self.staging_type,
            )
            raise

    @abstractmethod
    def write(
        self,
        table_name: str,
        data: DataFrame,
        staging_config: Mapping[str, Any],
    ) -> Any:
        """Write a table's curated rows to the staging destination; implemented by each staging type."""
        error = (
            f"Staging writer '{type(self).__name__}' does not "
            "implement write()."
        )
        logger.error(
            "Unsupported write operation for staging type '%s' "
            "and table '%s'",
            self.staging_type,
            table_name,
        )
        raise NotImplementedError(error)

    def supports(
        self,
        staging_config: Mapping[str, Any],
    ) -> bool:
        """Return whether this writer supports the given staging config; True by default."""
        try:
            logger.debug(
                "Default support check passed for staging type '%s'",
                self.staging_type,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to check support for staging type '%s'",
                self.staging_type,
            )
            raise

    def validate_configuration(
        self,
        staging_config: Mapping[str, Any],
    ) -> None:
        """Validate staging-specific configuration; no-op by default."""
        try:
            logger.debug(
                "No base configuration validation required for "
                "staging type '%s'",
                self.staging_type,
            )
        except Exception:
            logger.exception(
                "Failed to validate configuration for staging type '%s'",
                self.staging_type,
            )
            raise

    def metadata(self) -> Mapping[str, Any]:
        """Return descriptive metadata about this staging writer."""
        try:
            metadata = {
                "staging_type": self.staging_type,
            }
            logger.debug(
                "Generated metadata for staging type '%s'",
                self.staging_type,
            )
            return metadata
        except Exception:
            logger.exception(
                "Failed to generate metadata for staging type '%s'",
                self.staging_type,
            )
            raise
