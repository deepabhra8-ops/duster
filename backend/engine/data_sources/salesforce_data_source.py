"""Salesforce implementation of BaseDataSource: reads Salesforce objects via simple-salesforce + SOQL."""

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

# Salesforce date/datetime fields arrive from the REST API as ISO-8601 *strings*
# (e.g. "2026-08-17T12:46:40.000+0000"). createDataFrame does NOT parse those - with
# verifySchema=True (the default) Spark rejects them outright:
#
#   [CANNOT_ACCEPT_OBJECT_IN_TYPE] `TimestampType()` can not accept object
#   `2026-08-17T12:46:40.000+0000` in type `str`
#
# Mapping them here *without* converting the values is what broke every Salesforce
# run: every standard sObject carries CreatedDate/LastModifiedDate, and read()
# selects all fields by default, so the failure was total rather than occasional.
# read() now converts the values before building the DataFrame - see
# _convert_temporal_fields, which also decides the final per-field type.
#
# "time" is deliberately absent. Salesforce returns time-of-day values like
# "12:46:40.000Z" and Spark 3.5 has no TimeType, so text is the only honest target;
# it falls through to the StringType default in _build_spark_schema.
_SALESFORCE_TO_SPARK_TYPE = {
    "boolean": BooleanType(),
    "checkbox": BooleanType(),
    # LongType, not IntegerType: a Salesforce Number field allows up to 18 digits,
    # which overflows int32 and fails with the same CANNOT_ACCEPT_OBJECT_IN_TYPE
    # error the date fields hit. salesforce_type_mapping.map_salesforce_type already
    # labels these "BigInteger" for display - this keeps the two in step.
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

# Salesforce types whose text values must be converted into real Python
# date/datetime objects before Spark will accept them.
_TEMPORAL_SALESFORCE_TYPES = frozenset({"date", "datetime"})

# Distinguishes "this value is genuinely null" from "this text will not parse".
# Conflating the two would let a malformed value silently become a null, which is
# the failure mode date_inference.py argues is the worst one this product can have.
_UNPARSEABLE = object()

# Compound field types (Address, Geolocation) are a read-only *aggregate view* over sibling
# flat fields that already exist as independent, separately-typed fields in describe() -
# BillingAddress is backed by BillingStreet/BillingCity/BillingState/BillingPostalCode/
# BillingCountry/BillingStateCode/BillingCountryCode/BillingLatitude/BillingLongitude/
# BillingGeocodeAccuracy (already real fields); a custom My_Address__c field is likewise
# backed by Salesforce-auto-generated siblings (My_Address__City__s, My_Address__Street__s,
# ...). SOQL has no dot-notation for compound scalar fields (unlike genuine relationship
# fields) - attempting "BillingAddress.city" fails with SalesforceMalformedRequest ("Didn't
# understand relationship 'BillingAddress' in field path"). The fix is simply to skip
# selecting the compound aggregate field itself; its data is already fully covered by its
# sibling fields, which flow through the ordinary scalar-field path below with no special
# handling at all.
_COMPOUND_FIELD_TYPES = frozenset({"address", "location"})


def _iso_parse(value: Any) -> Any:
    """Parse ISO-8601 text into a datetime.

    Returns the datetime, None when the value is genuinely empty (a null), or
    _UNPARSEABLE when there is text that does not parse - the caller needs those
    three cases kept apart.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        return _UNPARSEABLE

    text = value.strip()

    if not text:
        return None

    try:
        # Python 3.11+ (the Glue 5.0 runtime) handles Salesforce's exact shape,
        # offset and all: "2026-08-17T12:46:40.000+0000", and plain "2026-08-17".
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    try:
        from dateutil.parser import isoparse

        return isoparse(text)
    except Exception:
        return _UNPARSEABLE


def _parse_datetime(value: Any) -> Any:
    """Parse a Salesforce datetime into a *naive UTC* datetime.

    Naive rather than timezone-aware on purpose. Spark renders a TimestampType in
    the session timezone, so an aware value would make Min/Max - and every rule
    that goes through cast("string"), i.e. DQ3/DQ6/DQ7 - shift with whatever
    timezone the Glue session happens to run in, making a run irreproducible
    across environments. Normalising to UTC here also matches DQ5, whose configured
    bounds are parsed naive; comparing an aware datetime against a naive one raises
    TypeError outside that rule's try block.
    """
    parsed = _iso_parse(value)

    if parsed is None or parsed is _UNPARSEABLE:
        return parsed

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def _parse_date(value: Any) -> Any:
    """Parse a Salesforce date ("2026-08-17") into a datetime.date."""
    parsed = _iso_parse(value)

    if parsed is None or parsed is _UNPARSEABLE:
        return parsed

    return parsed.date()


@register_source
class SalesforceDataSource(BaseDataSource):
    """Reads Salesforce objects as the data source, via simple-salesforce + SOQL."""

    source_type = "salesforce"

    def __init__(
        self,
        config: Mapping[str, Any],
        context,
    ) -> None:
        """Store config/context and defer client creation until first use."""
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
        """Read a Salesforce object into a DataFrame, optionally projecting columns.

        Compound aggregate fields (Address, Geolocation) are excluded from the SOQL SELECT -
        SOQL doesn't support dot-notation into them, and their data is already fully covered
        by sibling flat fields (BillingStreet, BillingCity, ... or, for a custom compound
        field, its auto-generated __s-suffixed siblings), which are read normally like any
        other field.
        """
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

            # query_all_iter streams result pages (following nextRecordsUrl)
            # instead of materialising every record first. query_all built the
            # complete record list AND then a second, equally large list of
            # normalised rows, so peak driver memory held two full copies of
            # the object; this holds one.
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

            # Salesforce hands back ISO-8601 *text* for date/datetime fields, which
            # Spark's schema verifier rejects. Convert in place: `rows` above is
            # already the single materialised copy of the object, and building a
            # second one would reintroduce exactly the peak-memory problem
            # query_all_iter was adopted to avoid.
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
                # An exhausted API allocation or a dead session is a condition
                # the operator can act on, not a defect - say so plainly rather
                # than surfacing the library's own wording.
                logger.error("Salesforce read failed: %s", friendly)
                raise RuntimeError(friendly) from exc

            logger.exception("Failed to read from Salesforce source")
            raise

    def table_exists(
        self,
        table_config: Mapping[str, Any],
    ) -> bool:
        """Return whether the configured Salesforce object exists."""
        try:
            self._describe(self._object_name(table_config))
            return True
        except Exception:
            logger.exception("Failed to check Salesforce object existence")
            return False

    def validate_configuration(self) -> None:
        """Validate that Salesforce credentials authenticate successfully."""
        try:
            self._get_client()
            logger.debug("Salesforce source configuration validated")
        except Exception:
            logger.exception("Salesforce source configuration validation failed")
            raise

    def close(self) -> None:
        """Release the Salesforce client and its underlying HTTP session.

        Dropping the reference alone left the requests.Session - and its pooled
        TCP connections - to garbage collection rather than closing them.
        """
        session = getattr(self._client, "session", None)

        if session is not None:
            try:
                session.close()
            except Exception:
                logger.warning("Failed to close the Salesforce HTTP session", exc_info=True)

        self._client = None

    def profiler_dependencies(self) -> Mapping[str, Any]:
        """Expose a field-type resolver so SalesforceProfiler can relabel dtypes for display
        with a Salesforce-native-type-to-SQL-type mapping (see salesforce_type_mapping.py)."""
        return {
            "field_type_resolver": self.get_field_types,
        }

    def get_field_types(self, object_name: str) -> dict[str, str]:
        """Return {field_name: raw Salesforce type string} for an object's queryable fields
        (compound aggregate fields excluded - see _COMPOUND_FIELD_TYPES), e.g.
        {'Status__c': 'picklist', 'BillingCity': 'string', 'BillingLatitude': 'double'}."""
        field_metadata = self._field_metadata(object_name)

        return {
            name: str(meta.get("type", "")).strip().lower()
            for name, meta in field_metadata.items()
            if str(meta.get("type", "")).strip().lower() not in _COMPOUND_FIELD_TYPES
        }

    def _get_client(self):
        """Return the lazily created Salesforce client, creating it on first use.

        Client creation logic is inlined here (rather than importing from
        services.connectors.salesforce_connector) because the engine package
        runs on AWS Glue where the backend ``services`` package is not available.
        """
        if self._client is None:
            details = self._get_db_config()
            domain = str(details.get("domain", "login")).strip()
            domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

            if domain == "login.salesforce.com":
                domain = "login"
            elif domain == "test.salesforce.com":
                domain = "test"

            # Supplying the session is what gives every Salesforce call a
            # timeout and bounded retries; simple_salesforce's own default
            # session has neither, so a hung endpoint would hang the whole Glue
            # run with nothing to reconcile it.
            self._client = Salesforce(
                username=details["username"],
                password=details["password"],
                security_token=details["security_token"],
                domain=domain,
                session=build_salesforce_session(),
            )

        return self._client

    def _get_db_config(self) -> Mapping[str, Any]:
        """Return the configured 'db' sub-config (Salesforce credentials)."""
        return self.config.get("db", {})

    def _describe(self, object_name: str) -> Mapping[str, Any]:
        """Return a Salesforce object's describe() metadata (fields, types, ...)."""
        return getattr(self._get_client(), object_name).describe()

    def _field_metadata(self, object_name: str) -> dict[str, Mapping[str, Any]]:
        """Return a Salesforce object's fields as {field_name: field_metadata}."""
        return {
            field["name"]: field
            for field in self._describe(object_name).get("fields", [])
        }

    @staticmethod
    def _object_name(table_config: Mapping[str, Any]) -> str:
        """Return the configured Salesforce object name, raising if it's missing."""
        object_name = str(table_config.get("name", "")).strip()

        if not object_name:
            raise ValueError(
                "Salesforce table configuration requires a 'name' value."
            )

        return object_name

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        """Normalize a Salesforce field value before handing it to Spark.

        Salesforce represents relationship fields as nested dicts and multi-select
        picklists as lists; the schema built here only has scalar column types, so
        both are flattened to their string representation. None (null) passes through.
        """
        if isinstance(value, (dict, list)):
            return str(value)

        return value

    @staticmethod
    def _exclude_compound_fields(
        field_names: list[str],
        field_metadata: Mapping[str, Mapping[str, Any]],
    ) -> list[str]:
        """Drop compound aggregate fields (type 'address'/'location') from a field list - see
        _COMPOUND_FIELD_TYPES for why: SOQL can't select them meaningfully, and their data is
        already covered by sibling flat fields queried normally alongside them."""
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
        """Convert date/datetime fields from ISO text to real date/datetime objects, in place.

        Returns the Spark type each converted field should actually be given, which
        is why this has to run *before* the schema is built rather than after: the
        type of a temporal field depends on whether its values parsed.

        A field whose text does not all parse keeps its original strings and is typed
        StringType. That is the deliberate trade: the run still completes, nothing is
        silently nulled, and the affected column simply behaves the way every
        Salesforce date column behaved before real temporal types were introduced
        (dtype label from describe(), Min/Max "Not Applicable"). Only the one bad
        column degrades - the rest of the object still gets real dates.
        """
        resolved: dict[str, DataType] = {}

        for field_name in field_names:
            salesforce_type = str(
                field_metadata.get(field_name, {}).get("type", "")
            ).strip().lower()

            if salesforce_type not in _TEMPORAL_SALESFORCE_TYPES:
                continue

            parse = _parse_date if salesforce_type == "date" else _parse_datetime

            # Converted values are held aside rather than written straight back, so
            # that a value found unparseable part-way through leaves every original
            # string in `rows` untouched. This is one column's worth of objects, not
            # a second copy of the table.
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
                # One warning per field, never per row: a wholly malformed column
                # would otherwise bury the Glue log in millions of identical lines.
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
        """Build a Spark schema from Salesforce describe() metadata, one field per column.

        `resolved_types` wins over the metadata-derived type for any field whose
        values were actually inspected - see _convert_temporal_fields, which
        downgrades a temporal field to StringType when its text will not parse.
        Anything absent from both (including Salesforce's "time", which has no Spark
        equivalent) falls back to StringType.
        """
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
