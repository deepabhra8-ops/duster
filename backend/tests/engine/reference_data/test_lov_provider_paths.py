"""LOV location resolution - the string handling only, no Spark and no S3.

The bug these cover: _resolve_path used to wrap every location in Path(), and
PurePosixPath collapses the "//" after a URI scheme. "s3://bucket/lov/x.csv"
became "s3:/bucket/lov/x.csv", which Spark cannot read, so every DQ8 rule on an
S3 deployment reported "check not run" against a file that was present and
correctly named. csv_data_source.py already avoided this; LovProvider did not.
"""

from pathlib import Path

import pytest

from engine.reference_data.lov_provider import LovProvider


S3_URI = "s3://datalytics-input/lov/3f0c1a2b_customer_lovs.csv"


class _Context:
    """The parts of ExecutionContext that LovProvider actually reads."""

    def __init__(self, lov_tables=None, reference_data=None):
        self._lov_tables = lov_tables or {}
        self.reference_data = reference_data or {}

    def get_metadata(self, key, default=None):
        if key == "lov_tables":
            return self._lov_tables
        return default


def _provider(**kwargs):
    provider = LovProvider.__new__(LovProvider)
    provider.context = _Context(**kwargs)
    provider._cache = {}
    return provider


def test_an_s3_uri_from_lov_tables_survives_resolution_intact():
    provider = _provider(lov_tables={"Customer.CustomerName": S3_URI})

    assert provider._resolve_path("Customer.CustomerName", None) == S3_URI


def test_an_unqualified_rule_parameter_still_reaches_the_s3_uri():
    """The profile map says `CustomerName`; the CSV header qualifies it."""
    provider = _provider(lov_tables={"Customer.CustomerName": S3_URI})

    assert provider._resolve_path("CustomerName", None) == S3_URI


def test_an_s3_uri_from_reference_config_survives_resolution_intact():
    provider = _provider()

    assert provider._resolve_path("Anything", {"path": S3_URI}) == S3_URI


def test_an_s3_uri_from_reference_data_survives_resolution_intact():
    provider = _provider(reference_data={"Gender": S3_URI})

    assert provider._resolve_path("Gender", None) == S3_URI


def test_an_s3_lov_reports_as_existing_without_touching_the_filesystem():
    provider = _provider(lov_tables={"Customer.CustomerName": S3_URI})

    assert provider.exists("CustomerName") is True


def test_a_local_file_resolves_to_a_path(tmp_path):
    lov_file = tmp_path / "lovs.csv"
    lov_file.write_text("Gender\nMale\n")

    provider = _provider(lov_tables={"Gender": str(lov_file)})
    resolved = provider._resolve_path("Gender", None)

    assert isinstance(resolved, Path)
    assert resolved == lov_file


def test_a_local_path_that_does_not_exist_falls_through(tmp_path):
    """A stale config entry must not shadow the other sources."""
    provider = _provider(
        lov_tables={"Gender": str(tmp_path / "gone.csv")},
        reference_data={"Gender": S3_URI},
    )

    assert provider._resolve_path("Gender", None) == S3_URI


def test_an_unresolvable_lov_raises():
    provider = _provider()

    with pytest.raises(FileNotFoundError):
        provider._resolve_path("Gender", None)


def test_an_unresolvable_lov_reports_as_not_existing():
    provider = _provider()

    assert provider.exists("Gender") is False
