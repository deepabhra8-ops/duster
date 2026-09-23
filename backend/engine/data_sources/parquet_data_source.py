"""Parquet implementation of BaseDataSource: reads Parquet files (whole or chunked) relative to the execution context base path."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping

from pyspark.sql import DataFrame

from engine.core.spark_session import get_spark_session
from engine.data_sources.base_data_source import BaseDataSource
from engine.data_sources.source_registry import register_source
from utils.logger import get_logger


logger = get_logger(__name__)


@register_source
class ParquetDataSource(BaseDataSource):
    """Reads Parquet files as the data source."""

    source_type = "parquet"

    def read(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ) -> DataFrame:
        """Read a Parquet file into a DataFrame, optionally projecting columns."""
        try:
            file_path = self._get_file_path(table_config)
            dataframe = get_spark_session().read.parquet(str(file_path))

            if columns:
                dataframe = dataframe.select(*columns)

            logger.info(
                "Read Parquet source '%s' (%s columns)",
                file_path,
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to read Parquet source")
            raise

    def read_chunks(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
        chunk_size: int = 0,
    ) -> Iterator[DataFrame]:
        """Read a Parquet file as a single Spark DataFrame (Spark partitions its own reads; there's no
        pandas-style chunked iteration to fall back to)."""
        yield self.read(
            table_config=table_config,
            columns=columns,
        )

    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the configured Parquet file exists."""
        try:
            file_path = self._get_file_path(table_config)
            exists = file_path.is_file()
            logger.debug("Checked Parquet source '%s': exists=%s", file_path, exists)
            return exists
        except Exception:
            logger.exception("Failed to check Parquet source existence")
            raise

    def get_columns(
        self,
        table_config: Mapping[str, Any],
    ) -> list[str]:
        """Return the Parquet file's column names."""
        return self.read(table_config).columns

    def get_row_count(
        self,
        table_config: Mapping[str, Any],
    ) -> int:
        """Return the Parquet file's row count."""
        return self.read(
            table_config=table_config,
        ).count()

    def supports_chunking(self) -> bool:
        """Parquet sources support chunked reads."""
        return True

    def validate_configuration(
        self,
    ) -> None:
        """Validate that a base_path is configured."""
        try:
            base_path = self.context.base_path

            if not base_path:
                raise ValueError(
                    "Parquet source requires a base_path."
                )
            logger.debug("Parquet source configuration validated")
        except Exception:
            logger.exception("Parquet source configuration validation failed")
            raise

    def _get_file_path(
        self,
        table_config: Mapping[str, Any],
    ) -> Path:
        """Resolve the Parquet file path from the table config and base path."""
        try:
            file_name = table_config.get("file", "")

            if not file_name:
                raise ValueError(
                    "Parquet table configuration requires a 'file' value."
                )

            return (
                Path(self.context.base_path)
                / str(file_name)
            )
        except Exception:
            logger.exception("Failed to resolve Parquet source file path")
            raise
