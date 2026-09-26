from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from repositories.dq_rule_repository import _is_duplicate_key, format_rule_id, parse_rule_id


def _integrity_error(message: str) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception(message))


def test_rule_ids_round_trip():
    assert format_rule_id(7) == "R007"
    assert format_rule_id(1234) == "R1234"
    assert parse_rule_id("R021") == 21
    assert parse_rule_id(" R1234 ") == 1234


def test_malformed_rule_ids_are_rejected():
    for value in ("", "21", "r021", "R", "R-1", "Rabc", None):
        assert parse_rule_id(value) is None


def test_only_unique_violations_count_as_name_conflicts():
    assert _is_duplicate_key(_integrity_error("Cannot insert duplicate key row in object 'dbo.dq_rules' (2601)"))
    assert _is_duplicate_key(_integrity_error("Violation of UNIQUE KEY constraint (2627)"))
    # A CHECK constraint failure is a bug, not a conflict, and must surface as one.
    assert not _is_duplicate_key(_integrity_error('conflicted with the CHECK constraint "chk_dq_rules_severity" (547)'))
