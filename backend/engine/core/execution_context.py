from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from utils.logger import get_logger
from utils.lov_naming import match_lov_name


logger = get_logger(__name__)

_REFERENCE_DATA_LOCK = threading.Lock()


@dataclass
class ExecutionContext:
    project_name: str
    run_timestamp: str
    mode: int = 1

    config: Mapping[str, Any] = field(default_factory=dict)

    source_type: str = ""
    base_path: str = ""

    source_config: Mapping[str, Any] = field(default_factory=dict)
    staging_config: Mapping[str, Any] = field(default_factory=dict)
    report_config: Mapping[str, Any] = field(default_factory=dict)

    rule_master: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )

    reference_data: Mapping[str, Any] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(default_factory=dict)

    def get_source_config(self, key: str, default: Any = None) -> Any:
        return self.source_config.get(key, default)

    def get_staging_config(self, key: str, default: Any = None) -> Any:
        return self.staging_config.get(key, default)

    def get_report_config(self, key: str, default: Any = None) -> Any:
        return self.report_config.get(key, default)

    def get_rule_definition(
        self,
        rule_id: str,
    ) -> Mapping[str, Any]:
        return self.rule_master.get(rule_id, {})

    def get_reference_data(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        if name in self.reference_data:
            return self.reference_data[name]

        with _REFERENCE_DATA_LOCK:
            if name in self.reference_data:
                return self.reference_data[name]

            loaded = self._load_lov(name)

            if loaded is None:
                return default

            self.set_reference_data(name, loaded)
            return loaded

    def _load_lov(self, name: str) -> Any | None:
        lov_tables = self.get_metadata("lov_tables", {})

        if not name or not lov_tables:
            return None

        resolved = match_lov_name(lov_tables, name)

        if resolved is None:
            logger.warning(
                "No LOV matches '%s' for project '%s'; the check will report as "
                "not run. Available LOVs: %s",
                name,
                self.project_name,
                ", ".join(sorted(str(key) for key in lov_tables)) or "none",
            )
            return None

        from engine.reference_data.lov_provider import LovProvider

        try:
            return LovProvider(self).get(resolved)
        except Exception:
            logger.warning(
                "Could not load LOV '%s' for project '%s'; the check will report "
                "as not run",
                name,
                self.project_name,
                exc_info=True,
            )
            return None

    def set_reference_data(
        self,
        name: str,
        value: Any,
    ) -> None:
        try:
            if isinstance(self.reference_data, dict):
                self.reference_data[name] = value
                logger.debug(
                    "Reference data '%s' stored for project '%s'",
                    name,
                    self.project_name,
                )
                return

            self.reference_data = {
                **self.reference_data,
                name: value,
            }
            logger.debug(
                "Reference data '%s' stored using a copied mapping "
                "for project '%s'",
                name,
                self.project_name,
            )
        except Exception:
            logger.exception(
                "Failed to store reference data '%s' for project '%s'",
                name,
                self.project_name,
            )
            raise

    def set_metadata(
        self,
        key: str,
        value: Any,
    ) -> None:
        try:
            self.metadata[key] = value
            logger.debug(
                "Metadata '%s' stored for project '%s'",
                key,
                self.project_name,
            )
        except Exception:
            logger.exception(
                "Failed to store metadata '%s' for project '%s'",
                key,
                self.project_name,
            )
            raise

    def get_metadata(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        return self.metadata.get(key, default)

    @property
    def is_profiling_mode(self) -> bool:
        return self.mode == 1

    @property
    def is_curation_mode(self) -> bool:
        return self.mode == 2

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        run_timestamp: str,
    ) -> "ExecutionContext":
        project_name = config.get(
            "project_name",
            "Project",
        )
        logger.info(
            "Creating execution context for project '%s'",
            project_name,
        )

        try:
            source = config.get("source", {})
            staging = config.get("staging", {})
            reports = config.get("reports", {})

            context = cls(
                project_name=project_name,
                run_timestamp=run_timestamp,
                mode=int(
                    config.get(
                        "run_mode",
                        1,
                    )
                ),
                config=config,
                source_type=source.get(
                    "type",
                    "",
                ),
                base_path=source.get(
                    "base_path",
                    "",
                ),
                source_config=source,
                staging_config=staging,
                report_config=reports,
                metadata={"lov_tables": dict(config.get("lov_tables", {}))},
            )
        except Exception:
            logger.exception(
                "Failed to create execution context for project '%s'",
                project_name,
            )
            raise

        logger.info(
            "Execution context created successfully: project='%s', mode=%s, "
            "source_type='%s'",
            context.project_name,
            context.mode,
            context.source_type,
        )
        return context
