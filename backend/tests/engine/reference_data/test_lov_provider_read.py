import pytest

from engine.reference_data.lov_provider import LovProvider


class _Context:
    def __init__(self, lov_tables):
        self._lov_tables = lov_tables
        self.reference_data = {}

    def get_metadata(self, key, default=None):
        if key == "lov_tables":
            return self._lov_tables
        return default


def _provider(lov_tables):
    provider = LovProvider.__new__(LovProvider)
    provider.context = _Context(lov_tables)
    provider._cache = {}
    return provider


def test_positional_names_are_generated_per_column():
    assert LovProvider._positional_names(3) == [
        "lov_column_0",
        "lov_column_1",
        "lov_column_2",
    ]


@pytest.mark.spark
def test_a_table_qualified_header_can_be_read(tmp_path, spark):
    lov = tmp_path / "customer_lovs.csv"
    lov.write_text(
        "Customer.CustomerName\n"
        "Matthew Meyer\n"
        "David Cox\n"
        "Michael Rich\n"
    )

    provider = _provider({"Customer.CustomerName": str(lov)})

    assert sorted(provider.get("CustomerName")) == [
        "David Cox",
        "Matthew Meyer",
        "Michael Rich",
    ]


@pytest.mark.spark
def test_the_right_column_of_a_wide_file_is_read(tmp_path, spark):
    lov = tmp_path / "job_lovs.csv"
    lov.write_text(
        "policy.status,claim.status,customer.gender\n"
        "Active,Open,Male\n"
        "Expired,Closed,Female\n"
        ",Reopened,\n"
    )

    tables = {
        name: str(lov)
        for name in ("policy.status", "claim.status", "customer.gender")
    }

    provider = _provider(tables)

    assert sorted(provider.get("policy.status")) == ["Active", "Expired"]
    assert sorted(provider.get("claim.status")) == ["Closed", "Open", "Reopened"]
    assert sorted(provider.get("customer.gender")) == ["Female", "Male"]


@pytest.mark.spark
def test_blank_cells_in_a_ragged_column_are_not_values(tmp_path, spark):
    lov = tmp_path / "ragged.csv"
    lov.write_text("a.short,b.long\nX,1\n,2\n,3\n")

    provider = _provider({"a.short": str(lov), "b.long": str(lov)})

    assert provider.get("a.short") == ["X"]
    assert sorted(provider.get("b.long")) == ["1", "2", "3"]


@pytest.mark.spark
def test_a_header_with_spaces_and_brackets_can_be_read(tmp_path, spark):
    lov = tmp_path / "odd.csv"
    lov.write_text("Customer [Legacy].Full Name\nAda Lovelace\n")

    provider = _provider({"Customer [Legacy].Full Name": str(lov)})

    assert provider.get("Customer [Legacy].Full Name") == ["Ada Lovelace"]
