from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseStagingWriter(ABC):
    staging_type: str = ""

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
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
