from __future__ import annotations

import io
from unittest.mock import patch

import polars as pl
import pytest

from services import profile_map_workbook_reader as mod


BLOCKED_DLL = ImportError(
    "DLL load failed while importing lib: An Application Control policy has blocked this file."
)


def _workbook_bytes() -> bytes:
    frame = pl.DataFrame(
        {
            "Column": ["claim_id", "claim_amount"],
            "Data Type": ["int", "decimal(18,2)"],
            "Applicable Rules": ["DQ1", "DQ4"],
        }
    )
    buffer = io.BytesIO()
    frame.write_excel(buffer, worksheet="claims")
    buffer.seek(0)
    return buffer.read()


class TestEngineFallback:
    def test_calamine_is_tried_first(self):
        tried = []
        real = pl.read_excel

        def spy(source, **kwargs):
            tried.append(kwargs.get("engine"))
            return real(source, **kwargs)

        with patch.object(mod.pl, "read_excel", side_effect=spy):
            mod.profile_map_workbook_reader.inspect(io.BytesIO(_workbook_bytes()))

        assert tried == ["calamine"], "the fast engine must not be skipped"

    def test_falls_back_to_openpyxl_when_the_native_engine_is_blocked(self):
        tried = []
        real = pl.read_excel

        def spy(source, **kwargs):
            engine = kwargs.get("engine")
            tried.append(engine)
            if engine == "calamine":
                raise BLOCKED_DLL
            return real(source, **kwargs)

        with patch.object(mod.pl, "read_excel", side_effect=spy):
            result = mod.profile_map_workbook_reader.inspect(io.BytesIO(_workbook_bytes()))

        assert tried == ["calamine", "openpyxl"]
        assert [t["table_name"] for t in result["tables"]] == ["claims"]
        assert len(result["tables"][0]["columns"]) == 2

    def test_the_stream_is_rewound_before_the_retry(self):
        seen_positions = []
        real = pl.read_excel

        def spy(source, **kwargs):
            seen_positions.append(source.tell())
            if kwargs.get("engine") == "calamine":
                source.read()
                raise BLOCKED_DLL
            return real(source, **kwargs)

        with patch.object(mod.pl, "read_excel", side_effect=spy):
            mod.profile_map_workbook_reader.inspect(io.BytesIO(_workbook_bytes()))

        assert seen_positions == [0, 0]

    def test_a_corrupt_workbook_still_fails(self):
        with pytest.raises(ValueError, match="Could not read workbook"):
            mod.profile_map_workbook_reader.inspect(io.BytesIO(b"this is not a workbook"))
