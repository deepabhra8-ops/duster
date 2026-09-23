"""Builds job configuration and runs the DQ pipeline in-process."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable

import yaml

from core.storage_layout import get_job_config_path
from repositories.job_repository import JobRepository
from services.config_builder import config_builder
from services import job_runner
from common.security.secret_redaction import redact_secrets
from utils.logger import get_logger


logger = get_logger(__name__)


class PipelineService:
    """Builds job configuration and runs the DQ engine for a job."""

    def run_job(
        self,
        job_id: str,
        params: dict[str, Any],
        update_job: Callable[..., None],
        log_job: Callable[[str, str], None],
        repository: JobRepository,
    ) -> None:
        """Run a job end to end: build its config, then run the engine in-process.

        Blocking - see JobService.submit_job(), which is what request handlers
        call instead: it hands this off to a background thread so the browser
        isn't left waiting on the whole run.
        """
        current = repository.get(job_id)

        if current and current.get("status") == "cancelled":
            log_job(job_id, "Job cancelled by user before it started")
            return

        update_job(job_id, status="running")
        log_job(job_id, "Job started")

        try:
            config = config_builder.build(job_id, params)

            # A redacted copy on disk for audit/debugging - never the real
            # connection_string/service_account_json. The run below executes off
            # the `config` object built above, not a re-read of this file.
            self._write_config(get_job_config_path(job_id), redact_secrets(config))

            step = str(params.get("step", "1"))

            job_runner.run(
                job_id=job_id,
                config=config,
                step=step,
                repository=repository,
                log_job=log_job,
            )

        except Exception as exc:
            current = repository.get(job_id)
            cancelled = bool(current and current.get("status") == "cancelled")

            if cancelled:
                log_job(job_id, "Job cancelled by user")
            else:
                log_job(job_id, f"ERROR: {exc}")
                log_job(job_id, traceback.format_exc())
                update_job(job_id, status="error")

    def _write_config(
        self,
        config_path: Path,
        config: dict[str, Any],
    ) -> None:
        """Write the pipeline configuration to disk as YAML (for audit/debugging)."""
        config_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with config_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            yaml.dump(
                config,
                file,
                sort_keys=False,
                allow_unicode=True,
            )


pipeline_service = PipelineService()
