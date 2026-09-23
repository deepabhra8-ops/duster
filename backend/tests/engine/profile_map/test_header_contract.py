"""Every header the app WRITES into a profile map must be one the engine READS.

The outage this pins: a validator job sourced from an uploaded workbook completed
successfully and produced an empty report and an empty Excel. Nothing errored,
nothing was logged as wrong, and the same workbook inspected correctly in the UI.

Cause: three modules kept parallel lists of accepted header spellings and drifted.
ProfileMapWriter and services/profile_map_exporter.py both write the rules column
as "Applicable Rule\n(Single ID)"; services/profile_map_workbook_reader.py (the
UI inspect) accepted it, but engine/profile_map/profile_map_reader.py (the one
the validator engine actually reads with) did not. Every column therefore parsed
with an empty rule_ids tuple, the run had zero checks to perform, and "no
findings" is indistinguishable from "nothing was checked" once it reaches the UI.

The stored-rows path was immune - profile_map_rows keys that field as plain
"Applicable Rules" - which is why a validator built from a Profile Mapper job
worked while the uploaded-workbook path silently produced nothing.
"""
from __future__ import annotations

import io

import pytest

from engine.profile_map.profile_map_reader import (
    CDE_HEADER_CANDIDATES,
    COLUMN_HEADER_CANDIDATES,
    PARAMETERS_HEADER_CANDIDATES,
    RULES_HEADER_CANDIDATES,
    ProfileMapReader,
)
from engine.profile_map.profile_map_writer import ProfileMapWriter
from services.profile_map_exporter import COLUMNS as EXPORTER_COLUMNS
from services.profile_map_exporter import profile_map_exporter


class TestWrittenHeadersAreReadable:
    """The writer and the reader are two halves of one file format."""

    def test_the_engine_writer_rules_header_is_accepted(self):
        assert ProfileMapWriter.RULES_HEADER in RULES_HEADER_CANDIDATES

    def test_the_engine_writer_cde_header_is_accepted(self):
        assert ProfileMapWriter.CDE_HEADER in CDE_HEADER_CANDIDATES

    def test_the_engine_writer_parameters_header_is_accepted(self):
        assert ProfileMapWriter.PARAMETERS_HEADER in PARAMETERS_HEADER_CANDIDATES

    @pytest.mark.parametrize(
        "candidates",
        [COLUMN_HEADER_CANDIDATES, CDE_HEADER_CANDIDATES, RULES_HEADER_CANDIDATES,
         PARAMETERS_HEADER_CANDIDATES],
        ids=["column", "cde", "rules", "parameters"],
    )
    def test_the_web_exporter_emits_a_header_the_engine_accepts(self, candidates):
        """The exporter is what produces the file a user downloads and re-uploads."""
        assert any(header in candidates for header in EXPORTER_COLUMNS)


class TestAnExportedWorkbookStillCarriesItsRules:
    """The end-to-end shape of the bug: download a profile map, feed it back."""

    @staticmethod
    def _row(table, column, rules):
        return {
            "Row ID": "r", "Table": table, "Column": column,
            "Data Type": "VARCHAR(255)", "CDE (X=Yes)": "X",
            "Applicable Rules": rules, "Rule Parameters": "",
            "Analyst Notes": "", "Total Count": "1", "Null Count": "0",
            "Null %": "0%", "Distinct Count": "1", "Unique %": "100%",
            "Min Value": "", "Max Value": "", "#": "1", "Enabled": "Y",
        }

    def test_rules_survive_the_export_read_round_trip(self, tmp_path):
        workbook = profile_map_exporter.build([
            self._row("Account", "Id", "DQ1, DQ2"),
            self._row("Account", "Name", "DQ3"),
        ])

        path = tmp_path / "Source_DQ_Profile_Map.xlsx"
        path.write_bytes(workbook)

        result = ProfileMapReader().read(path)
        columns = {c.column_name: c for c in result["Account"].columns}

        # Before the fix these were all empty tuples, so the validator had
        # nothing to check and reported a clean run against zero rules.
        assert columns["Id"].rule_ids == ("DQ1", "DQ2")
        assert columns["Name"].rule_ids == ("DQ3",)
        assert columns["Id"].cde is True

    def test_a_workbook_with_rules_never_parses_to_zero_checks(self, tmp_path):
        """The specific silent failure: rules present in the file, none read out."""
        path = tmp_path / "m.xlsx"
        path.write_bytes(profile_map_exporter.build([self._row("Account", "Id", "DQ1")]))

        result = ProfileMapReader().read(path)
        total_rules = sum(len(c.rule_ids) for c in result["Account"].columns)

        assert total_rules > 0, "a profile map with rules parsed to zero checks"
