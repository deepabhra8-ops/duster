from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
import xlsxwriter

from core.config import UPLOAD_ALLOWED_EXTENSIONS, UPLOAD_KINDS
from routes.job_routes import inspect_profile_map
from services.upload_file_saver import UploadFileSaver


def _workbook_bytes() -> bytes:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = book.add_worksheet("claims")

    for column, header in enumerate(["Table", "Column", "Applicable Rules"]):
        sheet.write(0, column, header)

    sheet.write(1, 0, "claim")
    sheet.write(1, 1, "claim_id")
    sheet.write(1, 2, "DQ1")

    book.close()
    return buffer.getvalue()


class TestUploadKindIsValid:
    def test_profile_map_is_a_configured_kind(self):
        assert "profile_map" in UPLOAD_KINDS
        assert "profile" not in UPLOAD_KINDS

    def test_the_kind_the_endpoint_uses_has_an_allow_list(self):
        assert UPLOAD_ALLOWED_EXTENSIONS.get("profile_map")

    def test_an_unknown_kind_would_reject_every_file(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            UploadFileSaver._validate_extension(kind="profile", filename="map.xlsx")


class TestExtensionValidation:
    def test_xlsx_is_accepted_for_profile_map(self):
        UploadFileSaver._validate_extension(kind="profile_map", filename="map.xlsx")

    @pytest.mark.parametrize("filename", ["map.csv", "map.txt", "map", "map.exe"])
    def test_other_extensions_are_still_rejected(self, filename):
        with pytest.raises(ValueError, match="Unsupported file type"):
            UploadFileSaver._validate_extension(kind="profile_map", filename=filename)

    def test_the_check_is_case_insensitive(self):
        UploadFileSaver._validate_extension(kind="profile_map", filename="MAP.XLSX")


class TestEndToEnd:
    def test_a_real_workbook_is_accepted_and_parsed(self, tmp_path, monkeypatch):
        from services import upload_file_saver as saver_module
        from services.profile_map_workbook_reader import profile_map_workbook_reader

        monkeypatch.setattr(
            saver_module, "get_upload_dir", lambda kind: tmp_path, raising=False
        )

        path = tmp_path / "map.xlsx"
        path.write_bytes(_workbook_bytes())

        result = profile_map_workbook_reader.inspect(path)

        assert result["tables"][0]["table_name"] == "claim"
        assert result["tables"][0]["columns"][0]["column_name"] == "claim_id"
        assert result["tables"][0]["columns"][0]["rule_ids"] == ["DQ1"]


class TestInspectReadsAStream:
    def test_a_workbook_is_parsed_from_an_in_memory_stream(self):
        from services.profile_map_workbook_reader import profile_map_workbook_reader

        result = profile_map_workbook_reader.inspect(io.BytesIO(_workbook_bytes()))

        assert result["tables"][0]["table_name"] == "claim"
        assert result["tables"][0]["columns"][0]["column_name"] == "claim_id"

    def test_a_stream_and_a_path_give_identical_results(self, tmp_path):
        from services.profile_map_workbook_reader import profile_map_workbook_reader

        path = tmp_path / "map.xlsx"
        path.write_bytes(_workbook_bytes())

        assert profile_map_workbook_reader.inspect(
            path
        ) == profile_map_workbook_reader.inspect(io.BytesIO(_workbook_bytes()))

    def test_a_non_workbook_stream_raises_a_value_error(self):
        from services.profile_map_workbook_reader import profile_map_workbook_reader

        with pytest.raises(ValueError, match="Could not read workbook"):
            profile_map_workbook_reader.inspect(io.BytesIO(b"definitely not xlsx"))


def _upload(data: bytes, filename: str = "map.xlsx"):
    from starlette.datastructures import UploadFile

    return UploadFile(filename=filename, file=io.BytesIO(data))


def _save(upload, kind="profile_map"):
    from services.upload_file_saver import UploadFileSaver

    return asyncio.run(UploadFileSaver().save(upload, kind=kind))


class TestSaverWritesAFile:
    def test_the_upload_is_written_to_disk(self, tmp_path, monkeypatch):
        from services import upload_file_saver as saver_module

        monkeypatch.setattr(
            saver_module, "get_upload_dir", lambda kind: tmp_path, raising=False
        )
        monkeypatch.setattr(
            saver_module, "get_upload_file_path", lambda kind, name: tmp_path / name
        )

        saved = _save(_upload(_workbook_bytes()))

        assert Path(saved["location"]).is_file()
        assert Path(saved["location"]).read_bytes() == _workbook_bytes()

    def test_an_oversized_upload_is_rejected(self, tmp_path):
        stream = io.BytesIO(b"x" * 50)
        destination = tmp_path / "out.bin"

        with pytest.raises(ValueError, match="exceeds"):
            UploadFileSaver._write_file(stream, destination, max_bytes=10)

        assert not destination.exists()


class TestInspectEndpoint:
    @staticmethod
    def _call(upload):
        class _FakeForm:
            def __init__(self, file):
                self._file = file

            def get(self, key):
                return self._file if key == "file" else None

        class _FakeRequest:
            def __init__(self, file):
                self._form = _FakeForm(file)

            async def form(self):
                return self._form

        return asyncio.run(
            inspect_profile_map(_FakeRequest(upload), username="tester")
        )

    @pytest.fixture(autouse=True)
    def local_uploads(self, tmp_path, monkeypatch):
        from services import upload_file_saver as saver_module

        monkeypatch.setattr(
            saver_module, "get_upload_dir", lambda kind: tmp_path, raising=False
        )
        monkeypatch.setattr(
            saver_module, "get_upload_file_path", lambda kind, name: tmp_path / name
        )

    def test_a_valid_workbook_is_stored_and_parsed(self):
        result = self._call(_upload(_workbook_bytes()))

        assert result["ok"] is True
        assert result["tables"][0]["table_name"] == "claim"
        assert result["filename"].endswith("_map.xlsx")

    def test_a_workbook_with_no_usable_columns_says_so(self):
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = book.add_worksheet("claims")
        sheet.write(0, 0, "Nothing")
        sheet.write(1, 0, "useful")
        book.close()

        response = self._call(_upload(buffer.getvalue()))

        assert response.status_code == 400
        assert b"No tables found" in response.body

    def test_a_non_xlsx_file_is_rejected_by_its_content_not_its_name(self):
        response = self._call(_upload(b"this is not a workbook"))

        assert response.status_code == 400
        assert b"valid .xlsx" in response.body

    def test_a_missing_file_is_a_400(self):
        response = self._call(None)

        assert response.status_code == 400
        assert b"No file uploaded" in response.body


class TestTableShapeGuard:
    @pytest.mark.parametrize(
        "tables",
        [
            ["claim", "member"],
            [{"schema": "public"}],
            [{"name": "   "}],
            [None],
            [["claim"]],
        ],
    )
    def test_malformed_entries_are_rejected(self, tables):
        from routes.job_routes import _tables_are_malformed

        assert _tables_are_malformed(tables) is True

    @pytest.mark.parametrize(
        "tables",
        [
            [],
            [{"name": "claim"}],
            [{"schema": "public", "name": "claim", "primary_key": "claim_id"}],
        ],
    )
    def test_well_formed_entries_are_accepted(self, tables):
        from routes.job_routes import _tables_are_malformed

        assert _tables_are_malformed(tables) is False

    def test_rowsToTables_output_shape_is_what_the_guard_accepts(self):
        from routes.job_routes import _tables_are_malformed

        produced = [{"schema": "public", "name": "claim", "primary_key": "claim_id"}]

        assert _tables_are_malformed(produced) is False


class TestTheUploadStreamIsNotReadAfterStorage:
    @staticmethod
    def _call(upload):
        class _FakeForm:
            def __init__(self, file):
                self._file = file

            def get(self, key):
                return self._file if key == "file" else None

        class _FakeRequest:
            def __init__(self, file):
                self._form = _FakeForm(file)

            async def form(self):
                return self._form

        return asyncio.run(inspect_profile_map(_FakeRequest(upload), username="tester"))

    @pytest.fixture(autouse=True)
    def local_uploads(self, tmp_path, monkeypatch):
        from services import upload_file_saver as saver_module

        monkeypatch.setattr(
            saver_module, "get_upload_dir", lambda kind: tmp_path, raising=False
        )
        monkeypatch.setattr(
            saver_module, "get_upload_file_path", lambda kind, name: tmp_path / name
        )

    def test_a_fully_consumed_upload_stream_is_survived(self):
        result = self._call(_upload(_workbook_bytes()))

        assert result["ok"] is True
        assert result["tables"][0]["table_name"] == "claim"

    def test_an_oversized_upload_is_still_rejected(self, monkeypatch):
        from routes import job_routes

        monkeypatch.setattr(job_routes, "MAX_UPLOAD_SIZE_BYTES", 10)

        response = self._call(_upload(_workbook_bytes()))

        assert response.status_code == 400
        assert b"exceeds" in response.body
