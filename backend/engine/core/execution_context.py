"""Defines ExecutionContext, the shared runtime state (project info, mode, source/staging/report config, rules, reference data) passed to every engine component for one pipeline run."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from utils.logger import get_logger
from utils.lov_naming import match_lov_name


logger = get_logger(__name__)

# Guards the lazy reference-data load. Module-level rather than per-instance
# because ExecutionContext is a frozen-ish dataclass shared by every engine
# component in a run, and one run has one context.
_REFERENCE_DATA_LOCK = threading.Lock()


@dataclass
class ExecutionContext:
    """Execution-scoped state shared across profiling and validation engine components."""

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
        """Return a value from the source configuration."""
        return self.source_config.get(key, default)

    def get_staging_config(self, key: str, default: Any = None) -> Any:
        """Return a value from the staging configuration."""
        return self.staging_config.get(key, default)

    def get_report_config(self, key: str, default: Any = None) -> Any:
        """Return a value from the report configuration."""
        return self.report_config.get(key, default)

    def get_rule_definition(
        self,
        rule_id: str,
    ) -> Mapping[str, Any]:
        """Return the rule master definition for a rule id."""
        return self.rule_master.get(rule_id, {})

    def get_reference_data(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """Return reference data by name, loading a configured LOV on first use.

        This used to be a bare dict lookup into a mapping that nothing ever
        populated, so it always returned the default. DQ8 and DQ9 read their
        reference data through here and treat "not found" as "cannot check",
        which meant both rules silently reported every row as passing on data
        they had never looked at.

        A LOV named in metadata["lov_tables"] is now resolved on demand through
        LovProvider (which understands both local paths and the s3:// URIs the
        Glue run discovers) and cached, so each file is read once per run.

        Reference *tables* for DQ9 are not resolved here: unlike LOVs, nothing
        in the job config yet says which connection and schema a reference table
        should be read from. Until that exists, DQ9 correctly reports NOT RUN
        rather than a fabricated pass.
        """
        if name in self.reference_data:
            return self.reference_data[name]

        # Tables are validated concurrently, so several threads can miss the
        # cache for the same LOV at once. Without this they would each read and
        # parse the same file; the second check inside the lock means only the
        # first one does.
        with _REFERENCE_DATA_LOCK:
            if name in self.reference_data:
                return self.reference_data[name]

            loaded = self._load_lov(name)

            if loaded is None:
                return default

            self.set_reference_data(name, loaded)
            return loaded

    def _load_lov(self, name: str) -> Any | None:
        """Load a LOV declared in metadata['lov_tables'], or None if there isn't one."""
        lov_tables = self.get_metadata("lov_tables", {})

        if not name or not lov_tables:
            return None

        # Not a bare `name in lov_tables`. lov_tables is keyed by the names the
        # uploaded CSVs declare in their column headers, which are routinely
        # qualified by table (`Customer.CustomerName`) where the profile map's
        # DQ8 parameter is not (`CustomerName`). An exact-key gate reported
        # "check not run" for a file that was present and correct.
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

        # Imported here, not at module scope: lov_provider imports this module,
        # so a top-level import would be circular.
        from engine.reference_data.lov_provider import LovProvider

        try:
            return LovProvider(self).get(resolved)
        except Exception:
            # Deliberately swallowed to a warning. The caller (DQ8) turns a None
            # into a NOT RUN result, which is the honest outcome - the check
            # could not be performed. Raising here would fail the whole table
            # over one unreadable reference file.
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
        """Store reference data for reuse by later operations in this run."""
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
        """Store a transient runtime metadata value."""
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
        """Return a stored runtime metadata value."""
        return self.metadata.get(key, default)

    @property
    def is_profiling_mode(self) -> bool:
        """Return whether this run is in profiling mode (mode 1)."""
        return self.mode == 1

    @property
    def is_curation_mode(self) -> bool:
        """Return whether this run is in curation/validation mode (mode 2)."""
        return self.mode == 2

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        run_timestamp: str,
    ) -> "ExecutionContext":
        """Build an ExecutionContext from a pipeline configuration mapping."""
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
                # {lov_name: path-or-s3-uri}. dq_glue_job.py discovers these by
                # listing the input bucket's lov/ prefix and has always put them
                # in the config; nothing read them until now, which is why DQ8
                # never found a reference list. LovProvider._resolve_path reads
                # this key.
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
