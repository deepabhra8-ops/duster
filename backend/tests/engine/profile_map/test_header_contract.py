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
        assert any(header in candidates for header in EXPORTER_COLUMNS)


class TestAnExportedWorkbookStillCarriesItsRules:
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

        assert columns["Id"].rule_ids == ("DQ1", "DQ2")
        assert columns["Name"].rule_ids == ("DQ3",)
        assert columns["Id"].cde is True

    def test_a_workbook_with_rules_never_parses_to_zero_checks(self, tmp_path):
        path = tmp_path / "m.xlsx"
        path.write_bytes(profile_map_exporter.build([self._row("Account", "Id", "DQ1")]))

        result = ProfileMapReader().read(path)
        total_rules = sum(len(c.rule_ids) for c in result["Account"].columns)

        assert total_rules > 0, "a profile map with rules parsed to zero checks"
