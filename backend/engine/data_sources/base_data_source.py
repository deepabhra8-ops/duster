from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from utils.logger import get_logger


logger = get_logger(__name__)


class BaseDataSource(ABC):
    source_type: str = ""

    def __init__(
        self,
        config: Mapping[str, Any],
        context: ExecutionContext,
    ) -> None:
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
        yield self.read(
            table_config=table_config,
            columns=columns,
        )

    @abstractmethod
    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
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
        return True

    def supports_chunking(self) -> bool:
        return False

    def profiler_dependencies(self) -> Mapping[str, Any]:
        return {}

    def metadata(self) -> Mapping[str, Any]:
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
        return None
