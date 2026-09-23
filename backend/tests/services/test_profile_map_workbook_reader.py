from __future__ import annotations

import pytest
import xlsxwriter

from services.profile_map_workbook_reader import ProfileMapWorkbookReader


def _workbook(tmp_path, sheets: dict[str, tuple[list[str], list[list]]]):
    path = tmp_path / "profile_map.xlsx"
    book = xlsxwriter.Workbook(str(path))

    for sheet_name, (headers, rows) in sheets.items():
        sheet = book.add_worksheet(sheet_name)

        for column, header in enumerate(headers):
            sheet.write(0, column, header)

        for row_index, row in enumerate(rows, start=1):
            for column, value in enumerate(row):
                if value is not None:
                    sheet.write(row_index, column, value)

    book.close()
    return path


HEADERS = ["Table", "Column", "Data Type", "CDE (X=Yes)", "Applicable Rules", "Rule Parameters", "Analyst Notes"]


@pytest.fixture
def reader():
    return ProfileMapWorkbookReader()


class TestBasicReading:
    def test_columns_and_rules_are_extracted(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (HEADERS, [
                ["claim", "claim_id", "bigint", "X", "DQ1", "", "primary key"],
                ["claim", "amount", "double", "", "DQ5", "0|100", ""],
            ]),
        })

        tables = reader.inspect(path)["tables"]

        assert len(tables) == 1
        assert tables[0]["table_name"] == "claim"
        assert [c["column_name"] for c in tables[0]["columns"]] == ["claim_id", "amount"]
        assert tables[0]["columns"][0]["rule_ids"] == ["DQ1"]
        assert tables[0]["columns"][1]["parameters"] == "0|100"

    def test_the_table_column_overrides_the_sheet_name(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "Sheet1": (HEADERS, [["real_table", "id", "int", "", "DQ1", "", ""]]),
        })

        assert reader.inspect(path)["tables"][0]["table_name"] == "real_table"

    def test_the_sheet_name_is_used_when_there_is_no_table_column(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "billing": (["Column", "Applicable Rules"], [["acct", "DQ1"]]),
        })

        assert reader.inspect(path)["tables"][0]["table_name"] == "billing"


class TestBlankCells:
    def test_a_blank_cell_never_becomes_the_string_nan(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (HEADERS, [["claim", "claim_id", None, None, "DQ1", None, None]]),
        })

        column = reader.inspect(path)["tables"][0]["columns"][0]

        assert column["data_type"] == ""
        assert column["analyst_notes"] == ""
        assert column["parameters"] == ""
        assert "nan" not in str(column).lower()

    def test_rows_without_a_column_name_are_skipped(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (HEADERS, [
                ["claim", "claim_id", "bigint", "", "DQ1", "", ""],
                ["claim", None, "", "", "DQ1", "", ""],
            ]),
        })

        assert len(reader.inspect(path)["tables"][0]["columns"]) == 1


class TestHeaderVariants:
    @pytest.mark.parametrize(
        "rules_header",
        ["Applicable Rules", "Applicable Rule\n(Single ID)", "Applicable Rules\n(comma-sep IDs)"],
    )
    def test_every_legacy_rules_header_is_accepted(self, reader, tmp_path, rules_header):
        path = _workbook(tmp_path, {
            "claims": (["Column", rules_header], [["claim_id", "DQ1"]]),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["rule_ids"] == ["DQ1"]

    def test_column_name_is_an_accepted_alias_for_column(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (["Column Name", "Applicable Rules"], [["claim_id", "DQ1"]]),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["column_name"] == "claim_id"

    def test_a_populated_legacy_header_wins_over_an_empty_current_one(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (
                ["Column", "Applicable Rule\n(Single ID)", "Applicable Rules"],
                [["claim_id", None, "DQ7"]],
            ),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["rule_ids"] == ["DQ7"]


class TestRuleSplitting:
    @pytest.mark.parametrize(
        "cell,expected",
        [
            ("DQ1|DQ2", ["DQ1", "DQ2"]),
            ("DQ1,DQ2", ["DQ1", "DQ2"]),
            ("DQ1;DQ2", ["DQ1", "DQ2"]),
            (" dq1 | dq2 ", ["DQ1", "DQ2"]),
            ("DQ1||DQ2", ["DQ1", "DQ2"]),
            ("", []),
        ],
    )
    def test_separators_and_casing(self, reader, tmp_path, cell, expected):
        path = _workbook(tmp_path, {
            "claims": (["Column", "Applicable Rules"], [["claim_id", cell or None]]),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["rule_ids"] == expected


class TestCdeFlag:
    @pytest.mark.parametrize("cell,expected", [
        ("X", True), ("x", True), ("Y", True), ("yes", True), ("TRUE", True), ("1", True),
        ("", False), (None, False), ("N", False), ("no", False),
    ])
    def test_cde_truthiness(self, reader, tmp_path, cell, expected):
        path = _workbook(tmp_path, {
            "claims": (["Column", "CDE (X=Yes)", "Applicable Rules"], [["claim_id", cell, "DQ1"]]),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["cde"] is expected


class TestSheetHandling:
    def test_the_instructions_sheet_is_ignored(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "Instructions": (["How to use"], [["fill this in"]]),
            "claims": (["Column", "Applicable Rules"], [["claim_id", "DQ1"]]),
        })

        tables = reader.inspect(path)["tables"]

        assert [t["table_name"] for t in tables] == ["claims"]

    def test_multiple_sheets_become_multiple_tables(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (["Column", "Applicable Rules"], [["claim_id", "DQ1"]]),
            "billing": (["Column", "Applicable Rules"], [["acct", "DQ1"]]),
        })

        assert {t["table_name"] for t in reader.inspect(path)["tables"]} == {"claims", "billing"}

    def test_a_sheet_with_no_usable_columns_is_dropped(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "empty_sheet": (["Column", "Applicable Rules"], [[None, "DQ1"]]),
            "claims": (["Column", "Applicable Rules"], [["claim_id", "DQ1"]]),
        })

        assert [t["table_name"] for t in reader.inspect(path)["tables"]] == ["claims"]


class TestTypePreservation:
    def test_a_numeric_looking_code_keeps_its_leading_zeros(self, reader, tmp_path):
        path = _workbook(tmp_path, {
            "claims": (["Column", "Applicable Rules"], [["00123", "DQ1"]]),
        })

        assert reader.inspect(path)["tables"][0]["columns"][0]["column_name"] == "00123"


class TestErrors:
    def test_an_unreadable_file_raises_a_clear_error(self, reader, tmp_path):
        broken = tmp_path / "not_really.xlsx"
        broken.write_text("this is not a workbook", encoding="utf-8")

        with pytest.raises(ValueError, match="Could not read workbook"):
            reader.inspect(broken)
