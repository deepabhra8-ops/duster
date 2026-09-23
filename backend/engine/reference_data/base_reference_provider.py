"""Defines the BaseReferenceProvider contract for looking up reference data (LOVs, reference tables) used by DQ rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from engine.core.execution_context import ExecutionContext
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseReferenceProvider(ABC):
    """Base class for a provider that resolves named reference data."""

    provider_type: str = ""

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
        """Store the execution context."""
        try:
            self.context = context
            logger.debug(
                "Initialized %s for provider type '%s'",
                type(self).__name__,
                self.provider_type,
            )
        except Exception:
            logger.exception(
                "Failed to initialize %s for provider type '%s'",
                type(self).__name__,
                self.provider_type,
            )
            raise

    @abstractmethod
    def get(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> Any:
        """Resolve and return the named reference data; implemented by each provider type."""
        logger.error(
            "Unsupported reference lookup for provider type '%s'",
            self.provider_type,
        )
        raise NotImplementedError(
            f"Provider '{type(self).__name__}' does not implement get()."
        )

    def exists(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the named reference data can be resolved."""
        try:
            self.get(
                reference_name=reference_name,
                reference_config=reference_config,
            )
            logger.debug(
                "Reference '%s' exists for provider type '%s'",
                reference_name,
                self.provider_type,
            )
            return True
        except Exception:
            logger.debug(
                "Reference '%s' does not exist for provider type '%s'",
                reference_name,
                self.provider_type,
                exc_info=True,
            )
            return False

    def validate_configuration(
        self,
        reference_config: Mapping[str, Any],
    ) -> None:
        """Validate provider-specific configuration; no-op by default."""
        try:
            logger.debug(
                "No base configuration validation required for provider type '%s'",
                self.provider_type,
            )
        except Exception:
            logger.exception(
                "Failed to validate configuration for provider type '%s'",
                self.provider_type,
            )
            raise

    def metadata(self) -> Mapping[str, Any]:
        """Return descriptive metadata about this provider."""
        try:
            metadata = {
                "provider_type": self.provider_type,
            }
            logger.debug(
                "Generated metadata for provider type '%s'",
                self.provider_type,
            )
            return metadata
        except Exception:
            logger.exception(
                "Failed to generate metadata for provider type '%s'",
                self.provider_type,
            )
            raise
