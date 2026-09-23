from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from repositories.profile_map_repository import ProfileMapVersionConflict
from services.profile_map_service import ProfileMapService


ROWS = [
    {
        "row_id": "uuid-1",
        "Table": "claim",
        "Column": "claim_id",
        "Data Type": "bigint",
        "CDE (X=Yes)": "",
        "Applicable Rules": "DQ1",
        "Rule Parameters": "",
        "Analyst Notes": "",
    },
    {
        "row_id": "uuid-2",
        "Table": "claim",
        "Column": "notes",
        "Data Type": "string",
        "CDE (X=Yes)": "",
        "Applicable Rules": "",
        "Rule Parameters": "",
        "Analyst Notes": "",
    },
]


@pytest.fixture
def service() -> ProfileMapService:
    return ProfileMapService()


def _stored(version: int = 1):
    return {"rows": [dict(r) for r in ROWS], "version": version, "row_count": len(ROWS)}


def _edit(row_id="uuid-1", **changes):
    return {"row_id": row_id, "changes": changes}


def test_rejects_non_editable_field(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ):
        with pytest.raises(ValueError, match="not editable"):
            service.apply_edits(
                "j1", 1, [_edit(**{"Data Type": "string"})], "alice"
            )


def test_rejects_unknown_rule_id(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ):
        with pytest.raises(ValueError, match="Unknown rule id: DQ99"):
            service.apply_edits(
                "j1", 1, [_edit(**{"Applicable Rules": "DQ99"})], "alice"
            )


def test_rejects_unknown_row_id(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ):
        with pytest.raises(ValueError, match="Unknown row_id"):
            service.apply_edits(
                "j1", 1, [_edit(row_id="nope", **{"Analyst Notes": "x"})], "alice"
            )


def test_rejects_overlong_text(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ):
        with pytest.raises(ValueError, match="limited to"):
            service.apply_edits(
                "j1", 1, [_edit(**{"Analyst Notes": "x" * 5000})], "alice"
            )


def test_analyst_notes_limit_is_200(service):
    assert service._validate_cell("Analyst Notes", "x" * 200) == "x" * 200

    with pytest.raises(ValueError, match="limited to 200 characters"):
        service._validate_cell("Analyst Notes", "x" * 201)


def test_rule_parameters_keep_the_larger_limit(service):
    assert service._validate_cell("Rule Parameters", "x" * 201) == "x" * 201


def test_normalizes_rule_ids(service):
    assert service._normalize_rule_ids(" dq1 ") == "DQ1"
    assert service._normalize_rule_ids("") == ""


def test_normalizes_cde_flag(service):
    assert service._normalize_cde("x") == "X"
    assert service._normalize_cde("true") == "X"
    assert service._normalize_cde("") == ""
    assert service._normalize_cde("no") == ""


def test_applies_edit_and_builds_audit(service):
    captured = {}

    def fake_apply(job_id, expected_version, rows, audit_entries, edited_by):
        captured.update(
            rows=rows, audit=audit_entries, by=edited_by, version=expected_version
        )
        return {"rows": rows, "version": expected_version + 1}

    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ), patch(
        "services.profile_map_service.profile_map_repository.apply_edits",
        side_effect=fake_apply,
    ):
        result = service.apply_edits(
            "j1", 1, [_edit(**{"CDE (X=Yes)": "x", "Analyst Notes": "key field"})], "alice"
        )

    assert result["version"] == 2

    edited = next(r for r in captured["rows"] if r["Column"] == "claim_id")
    assert edited["CDE (X=Yes)"] == "X"
    assert edited["Analyst Notes"] == "key field"

    assert captured["by"] == "alice"
    fields = {entry["field"] for entry in captured["audit"]}
    assert fields == {"CDE (X=Yes)", "Analyst Notes"}

    cde_entry = next(e for e in captured["audit"] if e["field"] == "CDE (X=Yes)")
    assert cde_entry["old_value"] == ""
    assert cde_entry["new_value"] == "X"
    assert cde_entry["table"] == "claim"
    assert cde_entry["column"] == "claim_id"


def test_rows_matched_by_row_id_not_index(service):
    reordered = {"rows": [dict(ROWS[1]), dict(ROWS[0])], "version": 1, "row_count": 2}
    captured = {}

    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=reordered,
    ), patch(
        "services.profile_map_service.profile_map_repository.apply_edits",
        side_effect=lambda **kw: captured.update(kw) or {"rows": kw["rows"], "version": 2},
    ):
        service.apply_edits("j1", 1, [_edit(row_id="uuid-1", **{"Analyst Notes": "hit"})], "alice")

    target = next(r for r in captured["rows"] if r["row_id"] == "uuid-1")
    other = next(r for r in captured["rows"] if r["row_id"] == "uuid-2")
    assert target["Analyst Notes"] == "hit"
    assert other["Analyst Notes"] == ""


def test_unchanged_value_is_a_noop_and_does_not_bump_version(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(version=7),
    ), patch(
        "services.profile_map_service.profile_map_repository.apply_edits"
    ) as apply_edits:
        result = service.apply_edits(
            "j1", 7, [_edit(**{"Applicable Rules": "DQ1"})], "alice"
        )

    apply_edits.assert_not_called()
    assert result["version"] == 7


def test_version_conflict_propagates(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=_stored(),
    ), patch(
        "services.profile_map_service.profile_map_repository.apply_edits",
        side_effect=ProfileMapVersionConflict(5, ROWS),
    ):
        with pytest.raises(ProfileMapVersionConflict) as excinfo:
            service.apply_edits("j1", 1, [_edit(**{"Analyst Notes": "x"})], "alice")

    assert excinfo.value.current_version == 5


def test_missing_profile_map_raises_keyerror(service):
    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill", return_value=None
    ):
        with pytest.raises(KeyError):
            service.apply_edits("j1", 1, [_edit(**{"Analyst Notes": "x"})], "alice")


def _addition(source_row_id="uuid-1", **changes):
    return {"source_row_id": source_row_id, "changes": changes}


def _apply(service, *, edits=None, additions=None, removals=None, stored=None, version=1):
    captured = {}

    with patch(
        "services.profile_map_service.profile_map_repository.get_or_backfill",
        return_value=stored or _stored(version),
    ), patch(
        "services.profile_map_service.profile_map_repository.apply_edits",
        side_effect=lambda **kw: captured.update(kw) or {"rows": kw["rows"], "version": version + 1},
    ):
        result = service.apply_edits(
            "j1",
            version,
            edits or [],
            "alice",
            additions=additions or [],
            removals=removals or [],
        )

    return result, captured


def _multi_rule_stored(version: int = 1):
    rows = [dict(r) for r in ROWS]
    second = dict(ROWS[0])
    second["row_id"] = "uuid-3"
    second["Applicable Rules"] = "DQ10"
    rows.insert(1, second)
    return {"rows": rows, "version": version, "row_count": len(rows)}


def test_added_row_clones_column_metadata_and_gets_a_server_side_row_id(service):
    _, captured = _apply(
        service,
        additions=[
            _addition(**{
                "Applicable Rules": "DQ5",
                "Rule Parameters": "1 | 99",
                "Analyst Notes": "range check",
            })
        ],
    )

    assert len(captured["rows"]) == len(ROWS) + 1

    added = next(r for r in captured["rows"] if r["Applicable Rules"] == "DQ5")
    assert added["Table"] == "claim"
    assert added["Column"] == "claim_id"
    assert added["Data Type"] == "bigint"
    assert added["Rule Parameters"] == "1 | 99"
    assert added["Analyst Notes"] == "range check"

    assert added["row_id"] not in {r["row_id"] for r in ROWS}
    assert uuid.UUID(added["row_id"])


def test_added_row_is_inserted_beside_its_column_not_appended(service):
    _, captured = _apply(service, additions=[_addition(**{"Applicable Rules": "DQ5"})])

    columns = [r["Column"] for r in captured["rows"]]
    assert columns == ["claim_id", "claim_id", "notes"]


def test_added_row_is_audited_as_an_addition(service):
    _, captured = _apply(service, additions=[_addition(**{"Applicable Rules": "DQ5"})])

    entry = next(e for e in captured["audit_entries"] if e["field"] == "(rule row added)")
    assert entry["old_value"] is None
    assert entry["new_value"] == "DQ5"
    assert entry["table"] == "claim"
    assert entry["column"] == "claim_id"
    assert uuid.UUID(entry["row_id"])


def test_edits_and_additions_apply_in_one_call(service):
    result, captured = _apply(
        service,
        edits=[_edit(row_id="uuid-2", **{"Analyst Notes": "edited"})],
        additions=[_addition(**{"Applicable Rules": "DQ5"})],
    )

    assert result["version"] == 2
    edited = next(r for r in captured["rows"] if r["row_id"] == "uuid-2")
    assert edited["Analyst Notes"] == "edited"
    assert any(r["Applicable Rules"] == "DQ5" for r in captured["rows"])


def test_rejects_addition_with_unknown_source_row(service):
    with pytest.raises(ValueError, match="Unknown source_row_id"):
        _apply(service, additions=[_addition(source_row_id="nope", **{"Applicable Rules": "DQ5"})])


def test_rejects_addition_without_a_rule(service):
    with pytest.raises(ValueError, match="needs an applicable rule"):
        _apply(service, additions=[_addition(**{"Analyst Notes": "no rule given"})])


def test_rejects_addition_with_unknown_rule_id(service):
    with pytest.raises(ValueError, match="Unknown rule id: DQ99"):
        _apply(service, additions=[_addition(**{"Applicable Rules": "DQ99"})])


def test_rejects_addition_setting_a_profiling_field(service):
    with pytest.raises(ValueError, match="cannot be set on an added rule row"):
        _apply(service, additions=[_addition(**{"Applicable Rules": "DQ5", "Total Count": "999"})])


def test_addition_alone_still_bumps_the_version(service):
    result, captured = _apply(service, edits=[], additions=[_addition(**{"Applicable Rules": "DQ5"})])

    assert result["version"] == 2
    assert captured["audit_entries"]


def test_rejects_a_rule_the_column_already_has(service):
    with pytest.raises(ValueError, match="already has a DQ1 rule"):
        _apply(service, additions=[_addition(**{"Applicable Rules": "DQ1"})])


def test_removes_one_rule_leaving_the_columns_others(service):
    _, captured = _apply(service, removals=["uuid-3"], stored=_multi_rule_stored())

    remaining = [r["row_id"] for r in captured["rows"]]
    assert "uuid-3" not in remaining
    assert "uuid-1" in remaining
    assert [r["Column"] for r in captured["rows"] if r["Column"] == "claim_id"] == ["claim_id"]


def test_removal_is_audited(service):
    _, captured = _apply(service, removals=["uuid-3"], stored=_multi_rule_stored())

    entry = next(e for e in captured["audit_entries"] if e["field"] == "(rule row removed)")
    assert entry["old_value"] == "DQ10"
    assert entry["new_value"] is None
    assert entry["column"] == "claim_id"


def test_refuses_to_remove_a_columns_last_rule(service):
    with pytest.raises(ValueError, match="must keep at least one rule"):
        _apply(service, removals=["uuid-2"])


def test_rejects_removal_of_unknown_row(service):
    with pytest.raises(ValueError, match="Unknown row_id"):
        _apply(service, removals=["nope"])


def test_removal_runs_before_additions_so_a_rule_can_be_swapped(service):
    _, captured = _apply(
        service,
        removals=["uuid-3"],
        additions=[_addition(**{"Applicable Rules": "DQ10", "Rule Parameters": "claim_id"})],
        stored=_multi_rule_stored(),
    )

    dq10 = [r for r in captured["rows"] if r["Applicable Rules"] == "DQ10"]
    assert len(dq10) == 1
    assert dq10[0]["row_id"] != "uuid-3"
    assert dq10[0]["Rule Parameters"] == "claim_id"
