"""A multi-table profile map must survive Excel's 31-character sheet-name limit.

A profile map carries one sheet per source table. Excel caps a worksheet name at
31 characters and forbids []:*?/\, so both writers sanitize and truncate - a
table called "Account_Contact_Relationship_History__c" lands on a sheet called
"Account_Contact_Relationship_Hi".

Two bugs followed from that, both only reachable with multiple (or long-named)
tables, which is why single-table testing never showed them:

  1. ProfileMapReader.read() keyed the profile map by SHEET name, while
     validation_engine looks each table up by the name in the job config (the
     real one). No entry was found, the table was skipped, and the run finished
     "successfully" having validated nothing for it. from_rows() - the path a
     validator sourced from a Profile Mapper job uses - already grouped by the
     "Table" column, so the two sources disagreed.

  2. profile_map_exporter did not deduplicate sheet names, so two tables sharing
     their first 31 characters raised DuplicateWorksheetName and failed the whole
     export. ProfileMapWriter already deduplicated; the exporter did not.
"""
from __future__ import annotations

import zipfile
import io
import re

import pytest

from engine.profile_map.profile_map_reader import ProfileMapReader
from services.profile_map_exporter import profile_map_exporter


LONG_TABLE = "Account_Contact_Relationship_History__c"  # 39 chars
ALPHA = "Customer_Account_Master_Record_Alpha"
BETA = "Customer_Account_Master_Record_Beta"  # shares ALPHA's first 31 chars


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
        """Establishes the premise - if Excel ever allowed longer names, the rest
        of this file would be testing nothing."""
        names = _sheet_names(profile_map_exporter.build([_row(LONG_TABLE)]))

        assert names == ["Account_Contact_Relationship_Hi"]
        assert len(names[0]) == 31

    def test_the_profile_map_is_keyed_by_the_real_table_name(self, tmp_path):
        """The bug: keyed by the truncated sheet name, validation_engine's
        `table_name not in profile_map` check skipped the table silently."""
        path = _written(tmp_path, [_row(LONG_TABLE), _row("Account")])

        assert set(ProfileMapReader().read(path)) == {LONG_TABLE, "Account"}

    def test_the_workbook_and_stored_row_paths_agree(self, tmp_path):
        """A validator can source its map from either; they must not disagree."""
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
        """Previously raised DuplicateWorksheetName and failed the whole download."""
        workbook = profile_map_exporter.build([_row(ALPHA), _row(BETA)])

        assert len(_sheet_names(workbook)) == 2

    def test_both_tables_survive_the_round_trip_under_their_real_names(self, tmp_path):
        path = _written(tmp_path, [_row(ALPHA), _row(BETA)])

        assert set(ProfileMapReader().read(path)) == {ALPHA, BETA}


class TestInstructionsSheet:
    def test_an_instructions_sheet_is_skipped_whatever_its_case(self, tmp_path):
        """The engine matched "Instructions" exactly while the web-side reader
        lowercased; a differently-cased sheet became a bogus table on one side."""
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
