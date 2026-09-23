from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from engine.data_sources.salesforce_data_source import SalesforceDataSource

OBJECT_NAME = "Account"


def _convert(fields: list[dict], rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    metadata = {field["name"]: field for field in fields}
    field_names = list(metadata)

    resolved = SalesforceDataSource._convert_temporal_fields(
        rows=rows,
        field_names=field_names,
        field_metadata=metadata,
        object_name=OBJECT_NAME,
    )

    return rows, {name: spark_type.simpleString() for name, spark_type in resolved.items()}


def _schema(fields: list[dict], rows: list[dict]) -> dict[str, str]:
    metadata = {field["name"]: field for field in fields}
    field_names = list(metadata)

    resolved = SalesforceDataSource._convert_temporal_fields(
        rows=rows,
        field_names=field_names,
        field_metadata=metadata,
        object_name=OBJECT_NAME,
    )
    schema = SalesforceDataSource._build_spark_schema(field_names, metadata, resolved)

    return {field.name: field.dataType.simpleString() for field in schema.fields}


class TestTemporalConversion:
    def test_a_salesforce_datetime_becomes_a_real_timestamp(self):
        rows, types = _convert(
            [{"name": "CreatedDate", "type": "datetime"}],
            [{"CreatedDate": "2026-08-17T12:46:40.000+0000"}],
        )

        assert types == {"CreatedDate": "timestamp"}
        assert rows[0]["CreatedDate"] == dt.datetime(2026, 8, 17, 12, 46, 40)
        assert rows[0]["CreatedDate"].tzinfo is None

    def test_an_offset_is_converted_to_utc_not_merely_dropped(self):
        rows, _ = _convert(
            [{"name": "CreatedDate", "type": "datetime"}],
            [{"CreatedDate": "2026-08-17T14:46:40.000+0200"}],
        )

        assert rows[0]["CreatedDate"] == dt.datetime(2026, 8, 17, 12, 46, 40)

    def test_a_zulu_suffix_is_handled(self):
        rows, _ = _convert(
            [{"name": "CreatedDate", "type": "datetime"}],
            [{"CreatedDate": "2026-08-17T12:46:40.123Z"}],
        )

        assert rows[0]["CreatedDate"] == dt.datetime(2026, 8, 17, 12, 46, 40, 123000)

    def test_a_salesforce_date_becomes_a_real_date(self):
        rows, types = _convert(
            [{"name": "CloseDate", "type": "date"}],
            [{"CloseDate": "2026-08-17"}],
        )

        assert types == {"CloseDate": "date"}
        assert rows[0]["CloseDate"] == dt.date(2026, 8, 17)

    def test_nulls_and_blanks_stay_null_without_downgrading_the_field(self):
        rows, types = _convert(
            [{"name": "CreatedDate", "type": "datetime"}],
            [
                {"CreatedDate": "2026-08-17T12:46:40.000+0000"},
                {"CreatedDate": None},
                {"CreatedDate": "   "},
            ],
        )

        assert types == {"CreatedDate": "timestamp"}
        assert [row["CreatedDate"] for row in rows] == [
            dt.datetime(2026, 8, 17, 12, 46, 40),
            None,
            None,
        ]

    def test_an_object_with_no_rows_still_resolves_a_real_type(self):
        _, types = _convert([{"name": "CreatedDate", "type": "datetime"}], [])

        assert types == {"CreatedDate": "timestamp"}


class TestUnparseableValuesFallBackToText:
    def test_the_field_is_read_as_text_with_every_value_preserved(self):
        rows, types = _convert(
            [{"name": "CreatedDate", "type": "datetime"}],
            [
                {"CreatedDate": "2026-08-17T12:46:40.000+0000"},
                {"CreatedDate": "last Tuesday"},
            ],
        )

        assert types == {"CreatedDate": "string"}
        assert [row["CreatedDate"] for row in rows] == [
            "2026-08-17T12:46:40.000+0000",
            "last Tuesday",
        ]

    def test_a_bad_value_after_the_first_row_still_rolls_the_field_back(self):
        rows, types = _convert(
            [{"name": "CloseDate", "type": "date"}],
            [
                {"CloseDate": "2026-08-17"},
                {"CloseDate": "2026-08-18"},
                {"CloseDate": "whenever"},
                {"CloseDate": "2026-08-19"},
            ],
        )

        assert types == {"CloseDate": "string"}
        assert all(isinstance(row["CloseDate"], str) for row in rows)

    def test_only_the_offending_field_degrades(self):
        _, types = _convert(
            [
                {"name": "CreatedDate", "type": "datetime"},
                {"name": "CloseDate", "type": "date"},
            ],
            [{"CreatedDate": "nonsense", "CloseDate": "2026-08-17"}],
        )

        assert types == {"CreatedDate": "string", "CloseDate": "date"}


class TestSchemaResolution:
    def test_a_time_field_stays_text_because_spark_has_no_time_type(self):
        assert _schema(
            [{"name": "PreferredCallTime__c", "type": "time"}],
            [{"PreferredCallTime__c": "12:46:40.000Z"}],
        ) == {"PreferredCallTime__c": "string"}

    def test_a_salesforce_int_is_a_bigint(self):
        assert _schema(
            [{"name": "ExternalId__c", "type": "int"}],
            [{"ExternalId__c": 123456789012345678}],
        ) == {"ExternalId__c": "bigint"}

    def test_an_unknown_salesforce_type_falls_back_to_text(self):
        assert _schema(
            [{"name": "Weird__c", "type": "somethingnew"}], [{"Weird__c": "x"}]
        ) == {"Weird__c": "string"}

    def test_ordinary_scalar_types_are_unchanged(self):
        assert _schema(
            [
                {"name": "Name", "type": "string"},
                {"name": "IsActive", "type": "boolean"},
                {"name": "Amount", "type": "currency"},
            ],
            [{"Name": "Acme", "IsActive": True, "Amount": 1.5}],
        ) == {"Name": "string", "IsActive": "boolean", "Amount": "double"}


@pytest.mark.spark
class TestReadEndToEnd:
    @staticmethod
    def _read(fields: list[dict], records: list[dict]):
        client = MagicMock()
        getattr(client, OBJECT_NAME).describe.return_value = {"fields": fields}
        client.query_all_iter.return_value = iter(records)

        source = SalesforceDataSource(config={"db": {}}, context=MagicMock())

        with patch.object(SalesforceDataSource, "_get_client", return_value=client):
            return source.read({"name": OBJECT_NAME})

    def test_an_object_with_date_fields_reads_without_a_type_error(self, spark):
        frame = self._read(
            [
                {"name": "Id", "type": "id"},
                {"name": "CreatedDate", "type": "datetime"},
                {"name": "CloseDate", "type": "date"},
            ],
            [
                {
                    "Id": "001xx",
                    "CreatedDate": "2026-08-17T12:46:40.000+0000",
                    "CloseDate": "2026-08-17",
                }
            ],
        )

        assert {f.name: f.dataType.simpleString() for f in frame.schema.fields} == {
            "Id": "string",
            "CreatedDate": "timestamp",
            "CloseDate": "date",
        }

        row = frame.collect()[0]
        assert row["CreatedDate"] == dt.datetime(2026, 8, 17, 12, 46, 40)
        assert row["CloseDate"] == dt.date(2026, 8, 17)

    def test_a_compound_address_field_is_excluded_from_the_read(self, spark):
        frame = self._read(
            [
                {"name": "BillingAddress", "type": "address"},
                {"name": "BillingCity", "type": "string"},
            ],
            [{"BillingCity": "Pune"}],
        )

        assert frame.schema.fieldNames() == ["BillingCity"]

    def test_min_max_are_real_dates_rather_than_not_applicable(self, spark):
        from engine.profiling.salesforce_profiler import SalesforceProfiler

        frame = self._read(
            [{"name": "CloseDate", "type": "date"}],
            [
                {"CloseDate": "2026-08-17"},
                {"CloseDate": "2024-01-05"},
                {"CloseDate": "2025-06-30"},
            ],
        )

        profiler = SalesforceProfiler(context=MagicMock(), field_type_resolver=None)
        column = profiler.profile(frame, {"name": OBJECT_NAME}).columns[0]

        assert column.min_value == dt.date(2024, 1, 5)
        assert column.max_value == dt.date(2026, 8, 17)
