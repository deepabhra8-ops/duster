from __future__ import annotations

from engine.core.result_models import RuleConfiguration, TableRuleConfiguration
from engine.profile_map.profile_map_reader import ProfileMapReader
from engine.profile_map.profile_map_rows import COLUMNS, build_rows


def _profile_map() -> dict[str, TableRuleConfiguration]:
    return {
        "claim": TableRuleConfiguration(
            table_name="claim",
            columns=(
                RuleConfiguration(
                    column_name="claim_id",
                    rule_ids=("DQ10", "DQ1"),
                    parameters="",
                    cde=True,
                    analyst_notes="primary key",
                    metadata={
                        "dtype": "bigint",
                        "total_count": 200,
                        "null_count": 0,
                        "distinct_count": 200,
                        "min_value": 1,
                        "max_value": 200,
                    },
                ),
                RuleConfiguration(
                    column_name="notes",
                    rule_ids=("DQ3",),
                    parameters="0,500",
                    cde=False,
                    analyst_notes="",
                    metadata={
                        "dtype": "string",
                        "total_count": 200,
                        "null_count": 50,
                        "distinct_count": 120,
                        "min_value": "Not Applicable",
                        "max_value": "Not Applicable",
                    },
                ),
            ),
        ),
        "member": TableRuleConfiguration(
            table_name="member",
            columns=(
                RuleConfiguration(
                    column_name="member_id",
                    rule_ids=("DQ1",),
                    parameters="",
                    cde=False,
                    analyst_notes="",
                    metadata={
                        "dtype": "bigint",
                        "total_count": 10,
                        "null_count": 1,
                        "distinct_count": 9,
                        "min_value": 1,
                        "max_value": 9,
                    },
                ),
            ),
        ),
    }


def test_build_rows_emits_one_row_per_column_with_expected_keys():
    rows = build_rows(_profile_map())

    assert len(rows) == 3
    assert all(set(row) == set(COLUMNS) for row in rows)
    assert {row["Table"] for row in rows} == {"claim", "member"}


def test_build_rows_derives_percentages():
    rows = build_rows(_profile_map())
    notes = next(r for r in rows if r["Column"] == "notes")

    assert notes["Null %"] == "25.00%"
    assert notes["Unique %"] == "60.00%"


def test_build_rows_guards_against_zero_total():
    empty = {
        "t": TableRuleConfiguration(
            table_name="t",
            columns=(
                RuleConfiguration(
                    column_name="c",
                    rule_ids=(),
                    parameters="",
                    cde=False,
                    analyst_notes="",
                    metadata={"total_count": 0, "null_count": 0, "distinct_count": 0},
                ),
            ),
        )
    }

    row = build_rows(empty)[0]
    assert row["Null %"] == "0.00%"
    assert row["Unique %"] == "0.00%"


def test_build_rows_renders_cde_as_x():
    rows = build_rows(_profile_map())

    assert next(r for r in rows if r["Column"] == "claim_id")["CDE (X=Yes)"] == "X"
    assert next(r for r in rows if r["Column"] == "notes")["CDE (X=Yes)"] == ""


def test_roundtrip_preserves_rules_cde_and_parameters():
    original = _profile_map()
    restored = ProfileMapReader().from_rows(build_rows(original))

    assert set(restored) == set(original)

    claim = {column.column_name: column for column in restored["claim"].columns}

    assert claim["claim_id"].cde is True
    assert set(claim["claim_id"].rule_ids) == {"DQ1", "DQ10"}
    assert claim["claim_id"].analyst_notes == "primary key"

    assert claim["notes"].cde is False
    assert claim["notes"].rule_ids == ("DQ3",)
    assert claim["notes"].parameters == "0,500"


def test_roundtrip_reflects_edited_rows():
    rows = build_rows(_profile_map())

    for row in rows:
        if row["Column"] == "notes":
            row["CDE (X=Yes)"] = "X"
            row["Applicable Rules"] = "DQ1, DQ3"

    restored = ProfileMapReader().from_rows(rows)
    notes = next(c for c in restored["claim"].columns if c.column_name == "notes")

    assert notes.cde is True
    assert set(notes.rule_ids) == {"DQ1", "DQ3"}


def test_from_rows_ignores_rows_without_a_table():
    restored = ProfileMapReader().from_rows(
        [{"Column": "orphan", "Applicable Rules": "DQ1"}]
    )

    assert restored == {}
