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
    def run_job(
        self,
        job_id: str,
        params: dict[str, Any],
        update_job: Callable[..., None],
        log_job: Callable[[str, str], None],
        repository: JobRepository,
    ) -> None:
        current = repository.get(job_id)

        if current and current.get("status") == "cancelled":
            log_job(job_id, "Job cancelled by user before it started")
            return

        update_job(job_id, status="running")
        log_job(job_id, "Job started")

        try:
            config = config_builder.build(job_id, params)

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
