"""Sniffs the first bytes of an uploaded file to catch content that contradicts its claimed extension.

Extension checks alone only stop a careless client - a renamed executable or
archive still passes them. This adds a cheap, allowlist-shaped second check
that runs after the extension is already known to be one we accept.
"""

from __future__ import annotations

# Signatures of binary formats that should never appear inside a file claiming
# to be plain-text CSV (executables, archives, PDFs, gzip). Not exhaustive -
# it's a tripwire for the common "malicious file renamed to .csv" case, not a
# full content-type classifier.
_BINARY_SIGNATURES = (
    b"MZ",  # Windows PE (.exe/.dll)
    b"\x7fELF",  # Linux ELF binary
    b"%PDF",
    b"PK\x03\x04",  # zip / xlsx / docx / jar ...
    b"PK\x05\x06",  # empty zip
    b"\x1f\x8b",  # gzip
)

_XLSX_SIGNATURES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
)


def sniff_mismatch(extension: str, header: bytes) -> str | None:
    """Return a rejection reason if `header` contradicts `extension`, else None.

    `extension` is the lowercase suffix (e.g. ".csv") the file was already
    validated to have; `header` is the first chunk of the file's bytes.
    """

    if extension == ".xlsx":
        if not header.startswith(_XLSX_SIGNATURES):
            return "File content is not a valid .xlsx (zip) archive"
        return None

    if extension == ".csv":
        if header.startswith(_BINARY_SIGNATURES) or b"\x00" in header:
            return "File content does not look like CSV text"
        return None

    return None
