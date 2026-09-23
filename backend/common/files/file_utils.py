"""Generic filesystem helpers (existence checks, listing, extensions, size/mtime, deletion) shared across the backend."""

from pathlib import Path
from typing import Iterable


def file_exists(path: Path | str) -> bool:
    """Return True if the path exists and is a file."""

    return Path(path).is_file()


def directory_exists(path: Path | str) -> bool:
    """Return True if the path exists and is a directory."""

    return Path(path).is_dir()


def ensure_directory(path: Path | str) -> Path:
    """Create a directory if it does not exist and return its path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_files(
    directory: Path | str,
    extension: str | None = None,
) -> list[Path]:
    """Return files from a directory, optionally filtered by extension."""

    directory = Path(directory)

    if not directory.is_dir():
        return []

    files = [
        path
        for path in directory.iterdir()
        if path.is_file()
    ]

    if extension:
        extension = extension.lower()
        files = [
            path
            for path in files
            if path.suffix.lower() == extension
        ]

    return sorted(files)


def list_filenames(
    directory: Path | str,
    extension: str | None = None,
) -> list[str]:
    """Return filenames from a directory."""

    return [
        path.name
        for path in list_files(directory, extension)
    ]


def get_file_extension(path: Path | str) -> str:
    """Return the lowercase file extension."""

    return Path(path).suffix.lower()


def get_filename_without_extension(path: Path | str) -> str:
    """Return the filename without its extension."""

    return Path(path).stem


def get_file_size(path: Path | str) -> int:
    """Return the file size in bytes."""

    return Path(path).stat().st_size


def get_file_modified_time(path: Path | str):
    """Return the file's last modification timestamp."""

    return Path(path).stat().st_mtime


def delete_file(path: Path | str) -> bool:
    """Delete a file if it exists and return whether it was deleted."""

    file_path = Path(path)

    if not file_path.is_file():
        return False

    file_path.unlink()
    return True


def find_files_by_extensions(
    directory: Path | str,
    extensions: Iterable[str],
) -> list[Path]:
    """Return files matching any of the supplied extensions."""

    normalized_extensions = {
        extension.lower()
        if extension.startswith(".")
        else f".{extension.lower()}"
        for extension in extensions
    }

    return [
        path
        for path in list_files(directory)
        if path.suffix.lower() in normalized_extensions
    ]
