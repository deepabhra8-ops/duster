from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pyspark.sql import DataFrame
from pyspark.sql.types import (
    BooleanType,
    DataType,
    DateType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from engine.core.spark_session import get_spark_session
from engine.data_sources.base_data_source import BaseDataSource
from engine.data_sources.source_registry import register_source
from simple_salesforce import Salesforce
from utils.logger import get_logger
from common.salesforce_session import build_salesforce_session, describe_salesforce_error


logger = get_logger(__name__)

_SALESFORCE_TO_SPARK_TYPE = {
    "boolean": BooleanType(),
    "checkbox": BooleanType(),
    "int": LongType(),
    "integer": LongType(),
    "long": LongType(),
    "double": DoubleType(),
    "currency": DoubleType(),
    "percent": DoubleType(),
    "number": DoubleType(),
    "summary": DoubleType(),
    "date": DateType(),
    "datetime": TimestampType(),
}

_TEMPORAL_SALESFORCE_TYPES = frozenset({"date", "datetime"})

_UNPARSEABLE = object()

_COMPOUND_FIELD_TYPES = frozenset({"address", "location"})


def _iso_parse(value: Any) -> Any:
    if value is None:
        return None

    if not isinstance(value, str):
        return _UNPARSEABLE

    text = value.strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    try:
        from dateutil.parser import isoparse

        return isoparse(text)
    except Exception:
        return _UNPARSEABLE


def _parse_datetime(value: Any) -> Any:
    parsed = _iso_parse(value)

    if parsed is None or parsed is _UNPARSEABLE:
        return parsed

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def _parse_date(value: Any) -> Any:
    parsed = _iso_parse(value)

    if parsed is None or parsed is _UNPARSEABLE:
        return parsed

    return parsed.date()


@register_source
class SalesforceDataSource(BaseDataSource):
    source_type = "salesforce"

    def __init__(
        self,
        config: Mapping[str, Any],
        context,
    ) -> None:
        super().__init__(
            config=config,
            context=context,
        )
        self._client = None

    def read(
        self,
        table_config: Mapping[str, Any],
        columns: list[str] | None = None,
    ) -> DataFrame:
        try:
            object_name = self._object_name(table_config)
            field_metadata = self._field_metadata(object_name)

            requested_field_names = (
                [column for column in columns if column in field_metadata]
                if columns
                else list(field_metadata.keys())
            )

            field_names = self._exclude_compound_fields(
                requested_field_names,
                field_metadata,
            )

            if not field_names:
                raise ValueError(
                    f"No queryable fields found for Salesforce object '{object_name}'."
                )

            soql = f"SELECT {', '.join(field_names)} FROM {object_name}"

            logger.info(
                "Reading Salesforce object '%s' (%s fields)",
                object_name,
                len(field_names),
            )

            rows = [
                {
                    field_name: self._normalize_value(record.get(field_name))
                    for field_name in field_names
                }
                for record in self._get_client().query_all_iter(soql)
            ]

            logger.info(
                "Read %s records from Salesforce object '%s'",
                len(rows),
                object_name,
            )

            resolved_types = self._convert_temporal_fields(
                rows=rows,
                field_names=field_names,
                field_metadata=field_metadata,
                object_name=object_name,
            )

            schema = self._build_spark_schema(
                field_names,
                field_metadata,
                resolved_types,
            )

            return get_spark_session().createDataFrame(rows, schema=schema)
        except Exception as exc:
            friendly = describe_salesforce_error(exc)

            if friendly:
                logger.error("Salesforce read failed: %s", friendly)
                raise RuntimeError(friendly) from exc

            logger.exception("Failed to read from Salesforce source")
            raise

    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        try:
            self._describe(self._object_name(table_config))
            return True
        except Exception:
            logger.exception("Failed to check Salesforce object existence")
            return False

    def validate_configuration(self) -> None:
        try:
            self._get_client()
            logger.debug("Salesforce source configuration validated")
        except Exception:
            logger.exception("Salesforce source configuration validation failed")
            raise

    def close(self) -> None:
        session = getattr(self._client, "session", None)

        if session is not None:
            try:
                session.close()
            except Exception:
                logger.warning("Failed to close the Salesforce HTTP session", exc_info=True)

        self._client = None

    def profiler_dependencies(self) -> Mapping[str, Any]:
        return {
            "field_type_resolver": self.get_field_types,
        }

    def get_field_types(self, object_name: str) -> dict[str, str]:
        field_metadata = self._field_metadata(object_name)

        return {
            name: str(meta.get("type", "")).strip().lower()
            for name, meta in field_metadata.items()
            if str(meta.get("type", "")).strip().lower() not in _COMPOUND_FIELD_TYPES
        }

    def _get_client(self):
        if self._client is None:
            details = self._get_db_config()
            domain = str(details.get("domain", "login")).strip()
            domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

            if domain == "login.salesforce.com":
                domain = "login"
            elif domain == "test.salesforce.com":
                domain = "test"

            self._client = Salesforce(
                username=details["username"],
                password=details["password"],
                security_token=details["security_token"],
                domain=domain,
                session=build_salesforce_session(),
            )

        return self._client

    def _get_db_config(self) -> Mapping[str, Any]:
        return self.config.get("db", {})

    def _describe(self, object_name: str) -> Mapping[str, Any]:
        return getattr(self._get_client(), object_name).describe()

    def _field_metadata(self, object_name: str) -> dict[str, Mapping[str, Any]]:
        return {
            field["name"]: field
            for field in self._describe(object_name).get("fields", [])
        }

    @staticmethod
    def _object_name(table_config: Mapping[str, Any]) -> str:
        object_name = str(table_config.get("name", "")).strip()

        if not object_name:
            raise ValueError(
                "Salesforce table configuration requires a 'name' value."
            )

        return object_name

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return str(value)

        return value

    @staticmethod
    def _exclude_compound_fields(
        field_names: list[str],
        field_metadata: Mapping[str, Mapping[str, Any]],
    ) -> list[str]:
        return [
            field_name
            for field_name in field_names
            if str(field_metadata.get(field_name, {}).get("type", "")).strip().lower()
            not in _COMPOUND_FIELD_TYPES
        ]

    @staticmethod
    def _convert_temporal_fields(
        rows: list[dict[str, Any]],
        field_names: list[str],
        field_metadata: Mapping[str, Mapping[str, Any]],
        object_name: str,
    ) -> dict[str, DataType]:
        resolved: dict[str, DataType] = {}

        for field_name in field_names:
            salesforce_type = str(
                field_metadata.get(field_name, {}).get("type", "")
            ).strip().lower()

            if salesforce_type not in _TEMPORAL_SALESFORCE_TYPES:
                continue

            parse = _parse_date if salesforce_type == "date" else _parse_datetime

            converted: list[Any] = []
            bad_value: Any = None
            bad_index = -1

            for index, row in enumerate(rows):
                value = parse(row.get(field_name))

                if value is _UNPARSEABLE:
                    bad_value = row.get(field_name)
                    bad_index = index
                    break

                converted.append(value)

            if bad_index >= 0:
                logger.warning(
                    "Salesforce object '%s': field '%s' (type '%s') holds a value at "
                    "record %s that is not ISO-8601 (%r). Reading the whole field as "
                    "text instead, so its values are preserved rather than nulled; "
                    "Min/Max for it will show as not applicable.",
                    object_name,
                    field_name,
                    salesforce_type,
                    bad_index,
                    bad_value,
                )
                resolved[field_name] = StringType()
                continue

            resolved[field_name] = (
                DateType() if salesforce_type == "date" else TimestampType()
            )

            for row, value in zip(rows, converted):
                row[field_name] = value

        return resolved

    @staticmethod
    def _build_spark_schema(
        field_names: list[str],
        field_metadata: Mapping[str, Mapping[str, Any]],
        resolved_types: Mapping[str, DataType] | None = None,
    ) -> StructType:
        resolved_types = resolved_types or {}

        return StructType(
            [
                StructField(
                    field_name,
                    resolved_types.get(
                        field_name,
                        _SALESFORCE_TO_SPARK_TYPE.get(
                            str(field_metadata.get(field_name, {}).get("type", "")).strip().lower(),
                            StringType(),
                        ),
                    ),
                    True,
                )
                for field_name in field_names
            ]
        )
