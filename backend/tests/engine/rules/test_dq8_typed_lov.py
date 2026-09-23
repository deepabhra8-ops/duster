import pytest

from engine.rules.dq8_lov import DQ8LOVRule
from engine.core.result_models import STATUS_KEY, STATUS_NOT_RUN


class _Context:
    def __init__(self, values):
        self._values = values

    def get_reference_data(self, name, default=None):
        return self._values


def _frame(spark, tmp_path, header, rows, schema):
    path = tmp_path / "data.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n")
    return spark.read.option("header", True).schema(schema).csv(str(path))


def _invalid_count(data, result):
    return data.filter(~result.pass_mask).count()


@pytest.mark.spark
def test_a_boolean_column_accepts_a_one_zero_reference_list(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "IsActive",
        ["true", "true", "false"],
        "IsActive boolean",
    )

    result = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_boolean_column_accepts_both_spellings_at_once(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "IsActive",
        ["true", "false", "true"],
        "IsActive boolean",
    )

    result = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1", "false"])
    )

    assert _invalid_count(data, result) == 0


@pytest.mark.spark
def test_a_boolean_column_still_rejects_a_list_that_does_not_fit(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "IsActive",
        ["true", "false"],
        "IsActive boolean",
    )

    result = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["Retail", "Wholesale"])
    )

    assert _invalid_count(data, result) == 2


@pytest.mark.spark
def test_a_string_column_is_untouched_by_boolean_folding(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "Flag",
        ["1", "true", "0"],
        "Flag string",
    )

    result = DQ8LOVRule().validate(
        data, "Flag", "Some.Flag", _Context(["1"])
    )

    assert _invalid_count(data, result) == 2


@pytest.mark.spark
def test_nulls_in_a_boolean_column_are_not_failed(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "IsActive",
        ["true", "", "false"],
        "IsActive boolean",
    )

    result = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1", "0"])
    )

    assert _invalid_count(data, result) == 0


@pytest.mark.spark
def test_an_int_column_matches_numeric_list_values(tmp_path, spark):
    data = _frame(spark, tmp_path, "Rating", ["1", "3", "7"], "Rating int")

    result = DQ8LOVRule().validate(
        data, "Rating", "Product.Rating", _Context(["1", "3", "5"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_decimal_column_ignores_written_scale(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "Price", ["10.50", "99.99"], "Price decimal(10,2)"
    )

    result = DQ8LOVRule().validate(
        data, "Price", "Product.Price", _Context(["10.5", "99.99"])
    )

    assert _invalid_count(data, result) == 0


@pytest.mark.spark
def test_a_date_column_matches_iso_list_values(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "LaunchDate",
        ["2024-01-01", "2024-06-30"],
        "LaunchDate date",
    )

    result = DQ8LOVRule().validate(
        data, "LaunchDate", "Product.LaunchDate", _Context(["2024-01-01"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_an_uncastable_value_does_not_silently_pass_other_rows(tmp_path, spark):
    data = _frame(spark, tmp_path, "Rating", ["1", "9"], "Rating int")

    result = DQ8LOVRule().validate(
        data, "Rating", "Product.Rating", _Context(["1", "not-a-number"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_padded_string_still_matches(tmp_path, spark):
    data = _frame(
        spark, tmp_path, "CustomerType", ["  Retail  ", "Trade"], "CustomerType string"
    )

    result = DQ8LOVRule().validate(
        data, "CustomerType", "Customer.CustomerType", _Context(["Retail"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_rule_with_no_lov_name_says_so(tmp_path, spark):
    data = _frame(spark, tmp_path, "Category", ["A"], "Category string")

    result = DQ8LOVRule().validate(data, "Category", "", _Context(["A"]))

    assert result.metadata[STATUS_KEY] == STATUS_NOT_RUN
    assert "No reference list named" in result.notes


@pytest.mark.spark
def test_each_column_is_compared_in_its_own_type_within_one_run(tmp_path, spark):
    path = tmp_path / "product.csv"
    path.write_text(
        "ProductName,IsActive,Price,LaunchDate\n"
        "Widget,true,10.50,2024-01-01\n"
        "Gadget,false,99.99,2024-06-30\n"
    )
    data = (
        spark.read.option("header", True)
        .schema(
            "ProductName string, IsActive boolean, "
            "Price decimal(10,2), LaunchDate date"
        )
        .csv(str(path))
    )

    lists = {
        "ProductName": ["Widget", "Gadget"],
        "IsActive": ["1", "0"],
        "Price": ["10.5", "99.99"],
        "LaunchDate": ["2024-01-01", "2024-06-30"],
    }

    for column, values in lists.items():
        result = DQ8LOVRule().validate(
            data, column, f"Product.{column}", _Context(values)
        )
        assert _invalid_count(data, result) == 0, column

    notes = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1", "0"])
    ).notes
    assert "compared as boolean" in notes
