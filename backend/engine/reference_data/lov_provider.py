from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


from engine.core.execution_context import ExecutionContext
from engine.reference_data.base_reference_provider import BaseReferenceProvider
from utils.lov_naming import match_lov_name
from utils.logger import get_logger


logger = get_logger(__name__)


class LovProvider(BaseReferenceProvider):
    provider_type = "lov"

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:
        super().__init__(context)
        self._cache: dict[str, list[str]] = {}

    def get(
        self,
        reference_name: str,
        reference_config: Mapping[str, Any] | None = None,
    ) -> list[str]:
        try:
            if reference_name in self._cache:
                logger.debug("Loaded LOV '%s' from cache", reference_name)
                return self._cache[reference_name]

            path = self._resolve_path(
                reference_name,
                reference_config,
            )

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

            column = self._select_column(
                df_spark.columns,
                reference_name,
            )

            header_name = str(column).strip()

            positional = self._positional_names(len(df_spark.columns))
            wanted = positional[df_spark.columns.index(column)]

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
        return [f"lov_column_{index}" for index in range(count)]

    @staticmethod
    def _select_column(
        columns: list[str],
        reference_name: str,
    ) -> str:
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
