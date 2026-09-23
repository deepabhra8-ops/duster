"""CSV implementation of BaseStagingWriter: writes curated rows to a "{table}_clean.csv" file."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from pyspark.sql import DataFrame

from engine.core.execution_context import ExecutionContext
from engine.staging.base_staging_writer import BaseStagingWriter
from engine.staging.staging_writer_registry import register_staging_writer
from utils.logger import get_logger


logger = get_logger(__name__)


@register_staging_writer
class CsvStagingWriter(BaseStagingWriter):
    """Writes curated rows to a CSV file in the configured staging directory."""

    staging_type = "csv"

    def write(
        self,
        table_name: str,
        data: DataFrame,
        staging_config: Mapping[str, Any],
    ) -> Path:
        """Write a table's curated rows to '{table_name}_clean.csv'."""
        try:
            output_directory = self._get_output_directory(
                staging_config
            )

            output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_path = (
                output_directory
                / f"{table_name}_clean.csv"
            )

            # Cache so the write below and the row-count log after it share one
            # materialization of `data` instead of each independently recomputing whatever
            # filter/transform chain produced it.
            cached = data.cache()

            try:
                self._write_single_csv(cached, output_path)
                row_count = cached.count()
            finally:
                cached.unpersist()

            logger.info(
                "CSV staging completed for table '%s': %s rows written to '%s'",
                table_name,
                row_count,
                output_path,
            )
            return output_path
        except Exception:
            logger.exception(
                "CSV staging failed for table '%s'",
                table_name,
            )
            raise

    @staticmethod
    def _write_single_csv(
        data: DataFrame,
        output_path: Path,
    ) -> None:
        """Write a Spark DataFrame to a single named CSV file at output_path.

        Spark's CSV writer always produces a directory of part-files (plus a _SUCCESS
        marker), not one named file, so this writes to a temporary sibling directory and
        moves the single part file into place - preserving the "one flat CSV file per
        table" contract downstream code (staging export, CSV globbing) relies on.
        """
        temp_directory = (
            output_path.parent
            / f".{output_path.stem}_{uuid.uuid4().hex}"
        )

        try:
            (
                data.coalesce(1).write
                .mode("overwrite")
                .option("header", True)
                .csv(str(temp_directory))
            )

            part_files = sorted(
                temp_directory.glob("part-*.csv")
            )

            if output_path.exists():
                output_path.unlink()

            if part_files:
                shutil.move(str(part_files[0]), str(output_path))
            else:
                # An empty DataFrame may not produce a part file at all.
                output_path.write_text("", encoding="utf-8")
        finally:
            shutil.rmtree(temp_directory, ignore_errors=True)

    def supports(
        self,
        staging_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the staging config requests CSV staging."""
        try:
            staging_type = str(
                staging_config.get(
                    "type",
                    "csv",
                )
            ).strip().lower()

            supported = staging_type == "csv"
            logger.debug(
                "CSV staging support check for type '%s': %s",
                staging_type,
                supported,
            )
            return supported
        except Exception:
            logger.exception(
                "Failed to check CSV staging support"
            )
            raise

    def validate_configuration(
        self,
        staging_config: Mapping[str, Any],
    ) -> None:
        """Validate that an output directory is configured or resolvable."""
        try:
            output_directory = self._get_output_directory(
                staging_config
            )

            if not output_directory:
                raise ValueError(
                    "CSV staging requires an output directory."
                )

            logger.debug(
                "CSV staging configuration validated for output directory '%s'",
                output_directory,
            )
        except Exception:
            logger.exception(
                "CSV staging configuration validation failed"
            )
            raise

    def _get_output_directory(
        self,
        staging_config: Mapping[str, Any],
    ) -> Path:
        """Resolve the CSV staging output directory from config or context metadata."""
        try:
            configured_path = staging_config.get(
                "output_dir",
                staging_config.get(
                    "output_directory",
                    staging_config.get(
                        "base_path",
                        "",
                    ),
                )
            )

            if configured_path:
                return Path(
                    str(configured_path)
                )

            metadata_path = self.context.get_metadata(
                "staging_output_dir",
                "",
            )

            if metadata_path:
                return Path(
                    str(metadata_path)
                )

            raise ValueError(
                "CSV staging output directory is not configured."
            )
        except Exception:
            logger.exception(
                "Failed to resolve CSV staging output directory"
            )
            raise
