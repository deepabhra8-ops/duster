"""DQ8 comparing against a LOV in the column's own type.

The bug these cover: every LOV value arrives from a CSV as text, and the
comparison used to happen in text too. A boolean column renders as "true", so a
list written as 1/0 matched nothing and reported every row invalid - 39 of 39 on
a column whose values were all legitimate. Casting each list value to the
column's type fixes that, and with it decimals written at a different scale and
dates; the uncastable case must still fail closed rather than pass silently.

DataFrames are read from CSV rather than built with createDataFrame: this
repository's Spark fixture cannot serialise Python objects to the JVM (see the
pre-existing failures in test_dq8_lov.py), and reading avoids that entirely.
"""

import pytest

from engine.rules.dq8_lov import DQ8LOVRule
from engine.core.result_models import STATUS_KEY, STATUS_NOT_RUN


class _Context:
    """Returns a fixed reference list, standing in for ExecutionContext."""

    def __init__(self, values):
        self._values = values

    def get_reference_data(self, name, default=None):
        return self._values


def _frame(spark, tmp_path, header, rows, schema):
    path = tmp_path / "data.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n")
    return spark.read.option("header", True).schema(schema).csv(str(path))


def _invalid_count(data, result):
    """Rows the mask rejects - what RuleExecutor fills in on the real run."""
    return data.filter(~result.pass_mask).count()


@pytest.mark.spark
def test_a_boolean_column_accepts_a_one_zero_reference_list(tmp_path, spark):
    """The reported case: LOV written as 1, column read back as boolean."""
    data = _frame(
        spark, tmp_path, "IsActive",
        ["true", "true", "false"],
        "IsActive boolean",
    )

    result = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1"])
    )

    # Only the false row is outside a list that allows just "1".
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
    """Folding 1/0 must not turn every list into a pass."""
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
    """Outside a boolean column, "1" means the string 1 and nothing else."""
    data = _frame(
        spark, tmp_path, "Flag",
        ["1", "true", "0"],
        "Flag string",
    )

    result = DQ8LOVRule().validate(
        data, "Flag", "Some.Flag", _Context(["1"])
    )

    # "true" and "0" are not the string "1".
    assert _invalid_count(data, result) == 2


@pytest.mark.spark
def test_nulls_in_a_boolean_column_are_not_failed(tmp_path, spark):
    """DQ8 judges membership; absence is DQ1's business."""
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
    """A list saying 10.5 must match a decimal(10,2) holding 10.50."""
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
    """`x IN (1, NULL)` is NULL, not false - that must not read as a pass."""
    data = _frame(spark, tmp_path, "Rating", ["1", "9"], "Rating int")

    result = DQ8LOVRule().validate(
        data, "Rating", "Product.Rating", _Context(["1", "not-a-number"])
    )

    # 9 is genuinely outside the list; the unusable entry must not excuse it.
    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_padded_string_still_matches(tmp_path, spark):
    """The text path keeps trimming both sides, as it always has."""
    data = _frame(
        spark, tmp_path, "CustomerType", ["  Retail  ", "Trade"], "CustomerType string"
    )

    result = DQ8LOVRule().validate(
        data, "CustomerType", "Customer.CustomerType", _Context(["Retail"])
    )

    assert _invalid_count(data, result) == 1


@pytest.mark.spark
def test_a_rule_with_no_lov_name_says_so(tmp_path, spark):
    """DQ8 is inferred for categorical-looking columns, often with no parameter."""
    data = _frame(spark, tmp_path, "Category", ["A"], "Category string")

    result = DQ8LOVRule().validate(data, "Category", "", _Context(["A"]))

    assert result.metadata[STATUS_KEY] == STATUS_NOT_RUN
    assert "No reference list named" in result.notes


@pytest.mark.spark
def test_each_column_is_compared_in_its_own_type_within_one_run(tmp_path, spark):
    """One LOV file, one table, four columns, four different types.

    The type is read per column from the DataFrame being validated, so nothing
    is configured per deployment and two jobs with different schemas each get
    their own answer - including the same column name typed differently.
    """
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

    # One wide LOV file would supply exactly these four lists.
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

    # And the type actually used is reported, per column.
    notes = DQ8LOVRule().validate(
        data, "IsActive", "Product.IsActive", _Context(["1", "0"])
    ).notes
    assert "compared as boolean" in notes
