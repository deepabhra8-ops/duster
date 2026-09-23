"""Defines the BaseDataSource contract: reading tables (whole or chunked), existence checks, and column/row metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseDataSource(ABC):
    """Base class for a data source that reads tables into DataFrames."""

    source_type: str = ""

    def __init__(
        self,
        config: Mapping[str, Any],
        context: ExecutionContext,
    ) -> None:
        """Store the source configuration and execution context."""
        try:
            self.config = config
            self.context = context
            logger.debug(
                "Initialized %s for source type '%s'",
                type(self).__name__,
                self.source_type,
            )
        except Exception:
            logger.exception(
                "Failed to initialize %s for source type '%s'",
                type(self).__name__,
                self.source_type,
            )
            raise

    @abstractmethod
    def read(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ) -> DataFrame:
        """Read a table into a DataFrame; implemented by each source type."""
        logger.error(
            "Unsupported read operation for source type '%s'",
            self.source_type,
        )
        raise NotImplementedError(
            f"Data source '{type(self).__name__}' does not implement read()."
        )

    def read_chunks(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
        chunk_size: int = 0,
    ) -> Iterator[DataFrame]:
        """Read a table in chunks, falling back to a single full read."""
        try:
            if chunk_size and chunk_size > 0:
                yield from self._read_chunks(
                    table_config=table_config,
                    columns=columns,
                    chunk_size=chunk_size,
                )
                return

            yield self.read(
                table_config=table_config,
                columns=columns,
            )
        except Exception:
            logger.exception(
                "Failed to read chunks for source type '%s'",
                self.source_type,
            )
            raise

    def _read_chunks(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None,
        chunk_size: int,
    ) -> Iterator[DataFrame]:
        """Default chunked-read fallback: yields one full read."""
        yield self.read(
            table_config=table_config,
            columns=columns,
        )

    @abstractmethod
    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the configured table exists; implemented by each source type."""
        logger.error(
            "Unsupported table existence check for source type '%s'",
            self.source_type,
        )
        raise NotImplementedError(
            "Data source does not implement table_exists()."
        )

    def get_columns(
        self,
        table_config: Mapping[str, Any],
    ) -> list[str]:
        """Return the table's column names."""
        try:
            dataframe = self.read(
                table_config=table_config,
            )
            return list(dataframe.columns)
        except Exception:
            logger.exception(
                "Failed to retrieve columns for source type '%s'",
                self.source_type,
            )
            raise

    def get_row_count(
        self,
        table_config: Mapping[str, Any],
    ) -> int:
        """Return the table's row count."""
        try:
            dataframe = self.read(
                table_config=table_config,
            )
            return dataframe.count()
        except Exception:
            logger.exception(
                "Failed to retrieve row count for source type '%s'",
                self.source_type,
            )
            raise

    def supports_columns_projection(self) -> bool:
        """Return whether this source can read a subset of columns."""
        return True

    def supports_chunking(self) -> bool:
        """Return whether this source supports chunked reads."""
        return False

    def profiler_dependencies(self) -> Mapping[str, Any]:
        """Return extra objects a profiler may need from this source."""
        return {}

    def metadata(self) -> Mapping[str, Any]:
        """Return descriptive metadata about this source."""
        try:
            return {
                "source_type": self.source_type,
            }
        except Exception:
            logger.exception(
                "Failed to generate metadata for source type '%s'",
                self.source_type,
            )
            raise

    def validate_configuration(self) -> None:
        """Validate source-specific configuration; no-op by default."""
        return None
