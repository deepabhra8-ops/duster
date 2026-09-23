from __future__ import annotations

import zipfile
import io
import re

import pytest

from engine.profile_map.profile_map_reader import ProfileMapReader
from services.profile_map_exporter import profile_map_exporter


LONG_TABLE = "Account_Contact_Relationship_History__c"
ALPHA = "Customer_Account_Master_Record_Alpha"
BETA = "Customer_Account_Master_Record_Beta"


def _row(table: str, column: str = "Id") -> dict:
    return {
        "Row ID": "r", "Table": table, "Column": column, "Data Type": "VARCHAR(255)",
        "CDE (X=Yes)": "X", "Applicable Rules": "DQ1", "Rule Parameters": "",
        "Analyst Notes": "", "Total Count": "1", "Null Count": "0", "Null %": "0%",
        "Distinct Count": "1", "Unique %": "100%", "Min Value": "", "Max Value": "",
        "#": "1", "Enabled": "Y",
    }


def _sheet_names(workbook_bytes: bytes) -> list[str]:
    xml = zipfile.ZipFile(io.BytesIO(workbook_bytes)).read("xl/workbook.xml")
    return [m.decode() for m in re.findall(rb'<sheet name="([^"]+)"', xml)]


def _written(tmp_path, rows):
    path = tmp_path / "profile_map.xlsx"
    path.write_bytes(profile_map_exporter.build(rows))
    return path


class TestLongTableNames:
    def test_the_sheet_name_really_is_truncated(self, tmp_path):
        names = _sheet_names(profile_map_exporter.build([_row(LONG_TABLE)]))

        assert names == ["Account_Contact_Relationship_Hi"]
        assert len(names[0]) == 31

    def test_the_profile_map_is_keyed_by_the_real_table_name(self, tmp_path):
        path = _written(tmp_path, [_row(LONG_TABLE), _row("Account")])

        assert set(ProfileMapReader().read(path)) == {LONG_TABLE, "Account"}

    def test_the_workbook_and_stored_row_paths_agree(self, tmp_path):
        rows = [_row(LONG_TABLE), _row("Account")]
        path = _written(tmp_path, rows)

        assert set(ProfileMapReader().read(path)) == set(
            ProfileMapReader().from_rows(rows)
        )

    def test_the_rules_land_on_the_right_table(self, tmp_path):
        path = _written(tmp_path, [_row(LONG_TABLE, "Id"), _row("Account", "Name")])

        result = ProfileMapReader().read(path)

        assert [r.column_name for r in result[LONG_TABLE].columns] == ["Id"]
        assert [r.column_name for r in result["Account"].columns] == ["Name"]


class TestCollidingTableNames:
    def test_two_tables_sharing_31_characters_still_export(self):
        workbook = profile_map_exporter.build([_row(ALPHA), _row(BETA)])

        assert len(_sheet_names(workbook)) == 2

    def test_both_tables_survive_the_round_trip_under_their_real_names(self, tmp_path):
        path = _written(tmp_path, [_row(ALPHA), _row(BETA)])

        assert set(ProfileMapReader().read(path)) == {ALPHA, BETA}


class TestInstructionsSheet:
    def test_an_instructions_sheet_is_skipped_whatever_its_case(self, tmp_path):
        import xlsxwriter

        path = tmp_path / "m.xlsx"
        book = xlsxwriter.Workbook(str(path))
        sheet = book.add_worksheet("INSTRUCTIONS")
        sheet.write(0, 0, "Column")
        sheet.write(1, 0, "not_a_real_column")
        data = book.add_worksheet("claim")
        for index, header in enumerate(["Table", "Column", "Applicable Rules"]):
            data.write(0, index, header)
        data.write_row(1, 0, ["claim", "claim_id", "DQ1"])
        book.close()

        assert set(ProfileMapReader().read(path)) == {"claim"}
