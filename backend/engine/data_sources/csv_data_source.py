from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.core.spark_session import get_spark_session
from engine.data_sources.base_data_source import BaseDataSource
from engine.data_sources.source_registry import register_source
from engine.profiling.date_inference import cast_date_columns
from utils.logger import get_logger


logger = get_logger(__name__)


@register_source
class CsvDataSource(BaseDataSource):
    source_type = "csv"

    def read(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ) -> DataFrame:
        try:
            file_path = self._get_file_path(table_config)

            dataframe = (
                get_spark_session().read
                .option("header", True)
                .option("inferSchema", True)
                .csv(str(file_path))
            )

            if columns:
                dataframe = dataframe.select(*columns)
                
            dataframe = cast_date_columns(dataframe)

            logger.info(
                "Read CSV source '%s' (%s columns)",
                file_path,
                len(dataframe.columns),
            )
            return dataframe
        except Exception:
            logger.exception("Failed to read CSV source")
            raise

    def read_chunks(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
        chunk_size: int = 0,
    ) -> Iterator[DataFrame]:
        yield self.read(
            table_config=table_config,
            columns=columns,
        )

    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        try:
            file_path = self._get_file_path(table_config)
            if isinstance(file_path, str) and file_path.startswith("s3://"):
                return True
            exists = Path(file_path).is_file()
            logger.debug("Checked CSV source '%s': exists=%s", file_path, exists)
            return exists
        except Exception:
            logger.exception("Failed to check CSV source existence")
            raise

    def get_columns(
        self,
        table_config: Mapping[str, Any],
    ) -> list[str]:
        return self.read(table_config).columns

    def get_row_count(
        self,
        table_config: Mapping[str, Any],
    ) -> int:
        return self.read(
            table_config=table_config,
        ).count()

    def supports_chunking(self) -> bool:
        return True

    def validate_configuration(
        self,
    ) -> None:
        try:
            base_path = self.context.base_path

            if not base_path:
                raise ValueError(
                    "CSV source requires a base_path."
                )
            logger.debug("CSV source configuration validated")
        except Exception:
            logger.exception("CSV source configuration validation failed")
            raise

    def _get_file_path(
        self,
        table_config: Mapping[str, Any],
    ) -> Path | str:
        try:
            file_name = table_config.get("file", "")

            if not file_name:
                raise ValueError(
                    "CSV table configuration requires a 'file' value."
                )

            base_path = str(self.context.base_path).strip()
            
            if base_path.startswith("s3://"):
                return f"{base_path.rstrip('/')}/{file_name}"
            
            return Path(base_path) / str(file_name)
        except Exception:
            logger.exception("Failed to resolve CSV source file path")
            raise

