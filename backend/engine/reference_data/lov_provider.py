"""Resolves and caches List of Values (LOV) CSV files used by the DQ8 rule."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


from engine.core.execution_context import ExecutionContext
from engine.reference_data.base_reference_provider import BaseReferenceProvider
from utils.lov_naming import match_lov_name
from utils.logger import get_logger


logger = get_logger(__name__)


class LovProvider(BaseReferenceProvider):
    """Loads and caches LOV values from configured CSV files."""

    provider_type = "lov"

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
        """Store the execution context and initialize the LOV cache."""
        super().__init__(context)
        self._cache: dict[str, list[str]] = {}

    def get(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Return the LOV's values, loading and caching them from CSV on first use."""
        try:
            if reference_name in self._cache:
                logger.debug("Loaded LOV '%s' from cache", reference_name)
                return self._cache[reference_name]

            path = self._resolve_path(
                reference_name,
                reference_config,
            )

            # Spark reads the file so both local paths and s3:// URIs work natively,
            # without needing a filesystem shim for object storage.
            from engine.core.spark_session import get_spark_session
            df_spark = (
                get_spark_session().read
                .option("header", True)
                .option("inferSchema", False)
                .csv(str(path))
            )

            if not df_spark.columns:
                raise ValueError(
                    f"LOV '{reference_name}' is empty."
                )

            # A LOV file is wide: every column is its own list, named by its
            # header. One upload therefore covers every DQ8-checked column in a
            # job, across as many tables as it likes. Single-column files still
            # work - they simply have one column to choose from.
            column = self._select_column(
                df_spark.columns,
                reference_name,
            )

            header_name = str(column).strip()

            # Selected by POSITION, not by name. Spark parses a column string as
            # a dotted path, so select("Customer.CustomerName") asks for field
            # CustomerName inside a struct called Customer and fails with
            # UNRESOLVED_COLUMN - even though a column of exactly that name is
            # sitting right there. LOV names are table-qualified by convention,
            # so a dot is the normal case here, not an edge one. Renaming every
            # column positionally sidesteps identifier parsing altogether, which
            # back-tick quoting would not: the header is user-supplied text and
            # may itself contain back-ticks, brackets or spaces.
            positional = self._positional_names(len(df_spark.columns))
            wanted = positional[df_spark.columns.index(column)]

            # The column's distinct values, collected straight to Python. This
            # used to go through toPandas(), which materialised the whole file
            # as a pandas DataFrame on the driver purely to read one column out
            # of it. The consumer (DQ8) only ever builds a set from these.
            values = [
                str(row[0]).strip()
                for row in (
                    df_spark.toDF(*positional)
                    .select(wanted)
                    .distinct()
                    .collect()
                )
                if row[0] is not None and str(row[0]).strip()
            ]

            if not values:
                raise ValueError(
                    f"LOV '{reference_name}' is empty."
                )

            self._cache[reference_name] = values

            if header_name:
                self._cache[header_name] = values

            logger.info(
                "Loaded LOV '%s' with %s values from '%s'",
                reference_name,
                len(values),
                path,
            )
            return values
        except Exception:
            logger.exception("Failed to load LOV '%s'", reference_name)
            raise

    def exists(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the named LOV's CSV file can be resolved."""
        try:
            path = self._resolve_path(
                reference_name,
                reference_config,
            )
            exists = isinstance(path, str) or path.is_file()
            logger.debug("Checked LOV '%s': exists=%s", reference_name, exists)
            return exists
        except (FileNotFoundError, ValueError):
            logger.debug(
                "LOV '%s' does not exist",
                reference_name,
                exc_info=True,
            )
            return False

    def clear_cache(self) -> None:
        """Clear all cached LOV values."""
        try:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Cleared %s cached LOV entries", count)
        except Exception:
            logger.exception("Failed to clear LOV cache")
            raise

    def preload(
        self,
        references: Mapping[str, Any],
    ) -> None:
        """Load and cache multiple LOVs up front, skipping any that fail."""
        try:
            for reference_name, reference_config in references.items():
                try:
                    self.get(
                        reference_name=reference_name,
                        reference_config=reference_config,
                    )
                except Exception:
                    logger.warning(
                        "Skipping failed LOV preload '%s'",
                        reference_name,
                        exc_info=True,
                    )
                    continue
        except Exception:
            logger.exception("Failed to preload LOV references")
            raise

    @staticmethod
    def _positional_names(count: int) -> list[str]:
        """Return placeholder column names that no Spark identifier parse can mangle."""
        return [f"lov_column_{index}" for index in range(count)]

    @staticmethod
    def _select_column(
        columns: list[str],
        reference_name: str,
    ) -> str:
        """Pick the column of a wide LOV file that a reference name refers to.

        A single-column file falls back to its only column, so the
        one-LOV-per-file uploads that predate wide files keep working even when
        their header and the rule's parameter are spelled differently.
        """
        matched = match_lov_name(columns, reference_name)

        if matched is not None:
            return matched

        if len(columns) > 1:
            raise ValueError(
                f"LOV '{reference_name}' does not match exactly one column in "
                f"the file. Available: {', '.join(str(c) for c in columns)}"
            )

        return columns[0]

    @staticmethod
    def _as_location(configured_path: Any) -> str | Path | None:
        """Return a readable location for a configured LOV, or None.

        An s3:// URI is returned as the string it already is. It must NOT go
        through pathlib: PurePosixPath collapses the "//" after the scheme, so
        "s3://bucket/lov/x.csv" becomes "s3:/bucket/lov/x.csv" - which Spark
        cannot read, and which no longer even satisfies the startswith("s3://")
        guards that were meant to protect it. That silently turned every LOV on
        an S3 deployment into a "check not run".

        A local path is returned only if it actually exists, so the caller can
        keep looking through its other sources.
        """
        location = str(configured_path or "").strip()

        if not location:
            return None

        if "://" in location:
            return location

        path = Path(location)

        return path if path.is_file() else None

    def _resolve_path(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None,
    ) -> str | Path:
        """Resolve an LOV's CSV location from its config, the context's lov_tables, or reference data."""
        if reference_config is not None:
            location = self._as_location(
                reference_config.get(
                    "path",
                    reference_config.get(
                        "file",
                        "",
                    ),
                )
            )

            if location is not None:
                return location

        configured_lovs = self.context.get_metadata(
            "lov_tables",
            {},
        )

        configured_key = match_lov_name(configured_lovs, reference_name)

        if configured_key is not None:
            location = self._as_location(configured_lovs[configured_key])

            if location is not None:
                return location

        reference_data = self.context.reference_data

        if reference_name in reference_data:
            configured_path = reference_data[reference_name]

            if isinstance(configured_path, (str, Path)):
                location = self._as_location(configured_path)

                if location is not None:
                    return location

        raise FileNotFoundError(
            f"LOV '{reference_name}' could not be resolved."
        )
