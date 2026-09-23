from __future__ import annotations

import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from engine.core.execution_context import ExecutionContext
from engine.profiling.profiling_engine import ProfilingEngine
from engine.profile_map.profile_map_writer import ProfileMapWriter
from utils.logger import get_logger


logger = get_logger(__name__)


class DQProfileMapper:
    def __init__(
        self,
        config: Mapping[str, Any],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        try:
            self.config = config
            self.progress_callback = progress_callback
            self.cancel_event = cancel_event
            self.context = ExecutionContext.from_config(
                config=config,
                run_timestamp=datetime.now().isoformat(
                    timespec="seconds"
                ),
            )
            self.engine = ProfilingEngine(context=self.context)
            self.writer = ProfileMapWriter()
            self.failed_tables: dict[str, str] = {}
            logger.debug("Initialized DQ profile mapper")
        except Exception:
            logger.exception("Failed to initialize DQ profile mapper")
            raise

    def generate_profile_map(self) -> dict[str, Any]:
        try:
            profile_result, profile_map = self.engine.profile_and_build_map(
                tables=self._get_tables(),
                progress_callback=self.progress_callback,
                cancel_event=self.cancel_event,
            )
            self.failed_tables = dict(profile_result.failed_tables)
            return profile_map
        except Exception:
            logger.exception("Profiling failed")
            raise

    def run(self) -> Path:
        try:
            profile_map = self.generate_profile_map()
            output_path = self._get_output_path()
            result = self.writer.write(
                profile_map=profile_map,
                path=output_path,
                project_name=self.context.project_name,
                run_timestamp=self.context.run_timestamp,
            )
            logger.info("Profile map creation completed: '%s'", result)
            return result
        except Exception:
            logger.exception("Profile map creation failed")
            raise

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

    def _get_output_path(self) -> Path:
        configured_path = self.config.get(
            "profile_map_file",
            "",
        )

        if configured_path:
            return Path(
                str(configured_path)
            )

        job_id = self.config.get(
            "job_id",
            "",
        )

        filename = (
            f"Source-DQ-Profile-Map_{job_id}.xlsx"
            if job_id
            else "Source-DQ-Profile-Map.xlsx"
        )

        return Path("output") / filename


def load_config(
    config_path: str | Path,
) -> dict[str, Any]:
    path = Path(config_path)

    try:
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

        logger.info("Loaded profile-mapper configuration '%s'", path)
        return config
    except Exception:
        logger.exception("Failed to load profile-mapper configuration '%s'", path)
        raise


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

    output_path = DQProfileMapper(
        config=config,
    ).run()

    print(
        f"Profile map created: {output_path}"
    )


if __name__ == "__main__":
    main()
