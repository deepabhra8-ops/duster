"""Date detection must never destroy a value.

The bug these guard against: cast_date_columns() sampled the first 100 rows,
picked any format parsing >80% of them, then applied it to the whole column with
to_date(). Non-matching values became NULL silently - so a CSV whose date format
drifted partway through, or whose sample happened to be unrepresentative, lost
data before any rule ran, and the tool then reported the resulting NULLs as
completeness failures. A data-quality product erasing the anomalies it exists to
find is the worst failure mode available to it.

The contract now: cast only when every non-blank value parses under exactly one
format; otherwise leave the column as text.
"""
from __future__ import annotations

import pytest

from engine.profiling.date_inference import cast_date_columns, detect_formats


pytestmark = pytest.mark.spark


def _column_type(data, column):
    return dict(data.dtypes)[column]


def _null_count(data, column):
    return data.filter(data[column].isNull()).count()


class TestNoSilentDataLoss:
    def test_a_late_format_change_does_not_null_anything(self, spark):
        """The headline regression.

        Rows 1-100 are yyyy-MM-dd and row 101 is dd/MM/yyyy. The old sampler saw
        only the first 100, chose yyyy-MM-dd, and nulled row 101.
        """
        rows = [(f"2023-01-{day:02d}",) for day in range(1, 29)]
        rows += [(f"2023-02-{day:02d}",) for day in range(1, 29)]
        rows += [(f"2023-03-{day:02d}",) for day in range(1, 29)]
        rows += [(f"2023-04-{day:02d}",) for day in range(1, 17)]
        assert len(rows) == 100
        rows.append(("31/12/2023",))

        data = spark.createDataFrame(rows, ["event_date"])

        result = cast_date_columns(data)

        # Nothing was parsed away, and the column kept every original value.
        assert _null_count(result, "event_date") == 0
        assert result.count() == 101
        assert _column_type(result, "event_date") == "string"

    def test_a_single_unparseable_value_prevents_the_cast(self, spark):
        data = spark.createDataFrame(
            [("2023-01-01",), ("2023-01-02",), ("not a date",)], ["event_date"]
        )

        result = cast_date_columns(data)

        assert _column_type(result, "event_date") == "string"
        assert _null_count(result, "event_date") == 0

    def test_garbage_is_never_cast(self, spark):
        data = spark.createDataFrame([("2023-13-45",), ("9999",)], ["event_date"])

        result = cast_date_columns(data)

        assert _column_type(result, "event_date") == "string"


class TestLosslessCasting:
    def test_a_fully_parseable_column_is_cast(self, spark):
        data = spark.createDataFrame(
            [("2023-01-01",), ("2023-06-15",), ("2023-12-31",)], ["event_date"]
        )

        result = cast_date_columns(data)

        assert _column_type(result, "event_date") == "date"
        assert _null_count(result, "event_date") == 0

    def test_a_timestamp_column_is_cast(self, spark):
        data = spark.createDataFrame(
            [("2023-01-01 10:30:00",), ("2023-06-15 23:59:59",)], ["event_at"]
        )

        result = cast_date_columns(data)

        assert _column_type(result, "event_at") == "timestamp"
        assert _null_count(result, "event_at") == 0

    def test_iso8601_with_an_offset_is_recognised(self, spark):
        """Absent from the old format list entirely, so it was left as text."""
        data = spark.createDataFrame(
            [("2023-01-01T10:30:00+05:30",), ("2023-06-15T23:59:59+00:00",)], ["event_at"]
        )

        assert detect_formats(data)["event_at"] is not None

    def test_nulls_and_blanks_do_not_block_a_cast(self, spark):
        """They are missing values, not malformed dates - DQ1's job, not this one's."""
        data = spark.createDataFrame(
            [("2023-01-01",), (None,), ("",), ("2023-06-15",)], "event_date: string"
        )

        result = cast_date_columns(data)

        assert _column_type(result, "event_date") == "date"
        # The two real dates survive; the null and the blank stay empty.
        assert result.filter(result["event_date"].isNotNull()).count() == 2


class TestAmbiguity:
    def test_a_genuinely_ambiguous_column_is_refused(self, spark):
        """01/02 and 03/04 mean different dates under dd/MM versus MM/dd.

        The old code silently preferred the US reading because MM/dd/yyyy was
        listed first, quietly mis-dating every row for a non-US source.
        """
        data = spark.createDataFrame([("01/02/2023",), ("03/04/2023",)], ["event_date"])

        assert detect_formats(data)["event_date"] is None
        assert _column_type(cast_date_columns(data), "event_date") == "string"

    def test_formats_that_tie_but_agree_are_not_ambiguous(self, spark):
        """A tie is only a problem when the readings differ.

        Every value here has day == month, so dd/MM and MM/dd produce identical
        dates and either is safe to use.
        """
        data = spark.createDataFrame([("03/03/2023",), ("07/07/2023",)], ["event_date"])

        assert detect_formats(data)["event_date"] is not None
        assert _column_type(cast_date_columns(data), "event_date") == "date"

    def test_an_unambiguous_day_first_column_is_cast(self, spark):
        """A day > 12 rules out the US reading, leaving one valid format."""
        data = spark.createDataFrame([("25/12/2023",), ("13/06/2023",)], ["event_date"])

        assert detect_formats(data)["event_date"] == "dd/MM/yyyy"


class TestNonDateColumns:
    def test_a_plain_text_column_is_untouched(self, spark):
        data = spark.createDataFrame([("OPEN",), ("CLOSED",)], ["status"])

        assert detect_formats(data)["status"] is None
        assert _column_type(cast_date_columns(data), "status") == "string"

    def test_an_all_null_column_is_not_cast(self, spark):
        data = spark.createDataFrame([(None,), (None,)], "event_date: string")

        assert detect_formats(data)["event_date"] is None

    def test_non_string_columns_are_ignored(self, spark):
        data = spark.createDataFrame([(1, "2023-01-01")], ["id", "event_date"])

        assert "id" not in detect_formats(data)

    def test_an_integer_id_is_never_read_as_an_epoch(self, spark):
        """Epoch seconds are excluded from the candidates precisely so that an
        ordinary numeric id stored as text is not reinterpreted as a date."""
        data = spark.createDataFrame([("1700000000",), ("1700000001",)], ["claim_id"])

        assert detect_formats(data)["claim_id"] is None


class TestSinglePass:
    def test_detection_reads_every_row_not_a_head_sample(self, spark):
        """The old implementation only ever looked at the first 100 rows.

        Here the first 200 rows are clean and the last one is not, so anything
        sampling the head would wrongly conclude the column is castable.
        """
        rows = [("2023-01-01",)] * 200 + [("garbage",)]
        data = spark.createDataFrame(rows, ["event_date"])

        assert detect_formats(data)["event_date"] is None
