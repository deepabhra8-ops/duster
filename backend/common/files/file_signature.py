from __future__ import annotations

_BINARY_SIGNATURES = (
    b"MZ",
    b"\x7fELF",
    b"%PDF",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"\x1f\x8b",
)

_XLSX_SIGNATURES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
)


def sniff_mismatch(extension: str, header: bytes) -> str | None:
    if extension == ".xlsx":
        if not header.startswith(_XLSX_SIGNATURES):
            return "File content is not a valid .xlsx (zip) archive"
        return None

    if extension == ".csv":
        if header.startswith(_BINARY_SIGNATURES) or b"\x00" in header:
            return "File content does not look like CSV text"
        return None

    return None
