from __future__ import annotations

from engine.rules.rule_parser import RuleParameterParser as Parser


def test_parse_splits_on_pipe_and_trims_whitespace():
    assert Parser.parse(" a | b |c ") == ["a", "b", "c"]


def test_parse_returns_an_empty_list_for_blank_or_none_input():
    assert Parser.parse("") == []
    assert Parser.parse("   ") == []
    assert Parser.parse(None) == []


def test_get_returns_the_value_at_a_position():
    assert Parser.get("a|b|c", position=1) == "b"


def test_get_returns_the_default_when_position_is_out_of_range():
    assert Parser.get("a", position=5, default="fallback") == "fallback"
    assert Parser.get("a", position=-1, default="fallback") == "fallback"


def test_get_int_parses_a_valid_integer():
    assert Parser.get_int("10|20", position=0, default=-1) == 10


def test_get_int_falls_back_to_default_for_invalid_or_missing_values():
    assert Parser.get_int("not_a_number", position=0, default=-1) == -1
    assert Parser.get_int("", position=0, default=-1) == -1


def test_get_float_parses_a_valid_float():
    assert Parser.get_float("3.5", position=0, default=-1.0) == 3.5


def test_get_float_falls_back_to_default_for_invalid_values():
    assert Parser.get_float("not_a_number", position=0, default=-1.0) == -1.0


def test_get_bool_recognizes_common_truthy_and_falsy_spellings():
    for truthy in ("true", "YES", "y", "1", "x"):
        assert Parser.get_bool(truthy, position=0) is True

    for falsy in ("false", "NO", "n", "0"):
        assert Parser.get_bool(falsy, position=0, default=True) is False


def test_get_bool_falls_back_to_default_for_unrecognized_values():
    assert Parser.get_bool("maybe", position=0, default=True) is True


def test_get_list_splits_on_the_given_separator():
    assert Parser.get_list("a,b, c", position=0) == ["a", "b", "c"]


def test_get_list_returns_empty_for_a_missing_position():
    assert Parser.get_list("only_one", position=5) == []


def test_as_dict_maps_positional_values_to_named_keys():
    result = Parser.as_dict("10|20", keys=["min", "max", "step"])
    assert result == {"min": "10", "max": "20", "step": ""}
