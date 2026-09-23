"""Unit tests for LOV name matching - pure string work, no Spark involved."""

from utils.lov_naming import match_lov_name


def test_an_exact_name_wins():
    assert match_lov_name(["Gender", "gender"], "gender") == "gender"


def test_case_differences_still_match():
    assert match_lov_name(["Customer.CustomerName"], "customer.CUSTOMERNAME") == (
        "Customer.CustomerName"
    )


def test_an_unqualified_parameter_matches_a_table_qualified_header():
    """The reported bug: the CSV header is qualified, the DQ8 parameter is not."""
    assert match_lov_name(["Customer.CustomerName"], "CustomerName") == (
        "Customer.CustomerName"
    )


def test_a_qualified_parameter_matches_an_unqualified_header():
    assert match_lov_name(["gender"], "Analytics.customer.gender") == "gender"


def test_an_ambiguous_trailing_segment_matches_nothing():
    """Guessing between two lists is worse than declining to validate."""
    assert match_lov_name(["Customer.Status", "Policy.Status"], "Status") is None


def test_an_unrelated_name_matches_nothing():
    assert match_lov_name(["Customer.CustomerName"], "PolicyType") is None


def test_an_empty_name_matches_nothing():
    assert match_lov_name(["Gender"], "") is None


def test_no_candidates_matches_nothing():
    assert match_lov_name([], "Gender") is None
