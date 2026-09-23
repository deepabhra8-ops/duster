from __future__ import annotations

import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from engine.core.execution_context import ExecutionContext
from engine.validation.validation_engine import ValidationEngine
from engine.profile_map.profile_map_reader import ProfileMapReader
from engine.reporting.report_builder import ReportBuilder
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger, log_and_reraise


logger = get_logger(__name__)


class DQValidator:
    @log_and_reraise(logger, "Failed to initialize DQ validator")
    def __init__(
        self,
        config: Mapping[str, Any],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event

        self.context = ExecutionContext.from_config(
            config=config,
            run_timestamp=datetime.now().isoformat(
                timespec="seconds"
            ),
        )

        self.engine = ValidationEngine(
            context=self.context,
        )

        self.profile_map_reader = ProfileMapReader()
        self.report_builder = ReportBuilder()
        logger.debug("Initialized DQ validator")

    @log_and_reraise(logger, "DQ validation failed")
    def run(self) -> Path:
        _, result = self.validate_and_report()
        return result

    @log_and_reraise(logger, "DQ validation failed")
    def validate_and_report(self) -> tuple[Any, Path]:
        profile_map = self._load_profile_map()

        validation_result = self.engine.validate(
            tables=self._get_tables(),
            profile_map=profile_map,
            progress_callback=self.progress_callback,
            cancel_event=self.cancel_event,
        )

        if self.cancel_event is not None and self.cancel_event.is_set():
            raise JobCancelledError("Job cancelled by user")

        output_path = self._get_output_path()

        result = self.report_builder.write(
            validation_result=validation_result,
            output_path=output_path,
        )

        self._release_cached_sources(validation_result)

        logger.info("DQ validation completed: '%s'", result)
        return validation_result, result

    @staticmethod
    def _release_cached_sources(validation_result) -> None:
        for table_result in validation_result.tables.values():
            cached_source = table_result.metadata.get("_cached_source")

            if cached_source is not None:
                cached_source.unpersist()

    def _load_profile_map(self):
        rows = self.config.get("profile_map_rows")

        if rows:
            logger.info(
                "Loading profile map from %s supplied rows (no workbook read)",
                len(rows),
            )
            return self.profile_map_reader.from_rows(rows)

        profile_map_path = self._get_profile_map_path()

        return self.profile_map_reader.read(
            profile_map_path
        )

    def _get_tables(self) -> list[Mapping[str, Any]]:
        source_config = self.config.get(
            "source",
            {},
        )

        tables = source_config.get(
            "tables",
            [],
        )

        if not isinstance(tables, list):
            raise ValueError(
                "source.tables must be a list."
            )

        return tables

    def _get_profile_map_path(self) -> Path:
        configured_path = self.config.get(
            "profile_map_file",
            "",
        )

        if configured_path:
            return Path(
                str(configured_path)
            )

        raise ValueError(
            "Profile map file is not configured."
        )

    def _get_output_path(self) -> Path:
        reports_config = self.config.get(
            "reports",
            {},
        )

        configured_report_file = reports_config.get(
            "report_file",
            "",
        )

        if configured_report_file:
            return Path(
                str(configured_report_file)
            )

        configured_directory = reports_config.get(
            "output_path",
            "",
        )

        if configured_directory:
            return (
                Path(str(configured_directory))
                / self._default_report_filename()
            )

        raise ValueError(
            "Validation report output path is not configured."
        )

    def _default_report_filename(self) -> str:
        job_id = self.config.get(
            "job_id",
            "",
        )

        if job_id:
            return f"DQ-Validation-Report_{job_id}.xlsx"

        return "DQ-Validation-Report.xlsx"


@log_and_reraise(
    logger,
    lambda config_path, **_: (
        "Failed to load validation configuration '%s'",
        config_path,
    ),
)
def load_config(
    config_path: str | Path,
) -> dict[str, Any]:
    path = Path(config_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(
            "Configuration must contain a YAML mapping."
        )

    logger.info("Loaded validation configuration '%s'", path)
    return config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        required=True,
    )

    args = parser.parse_args()

    config = load_config(
        args.config
    )

    output_path = DQValidator(
        config=config,
    ).run()

    print(
        f"DQ validation report created: {output_path}"
    )


if __name__ == "__main__":
    main()
