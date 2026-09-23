from pathlib import Path
from typing import Iterable


def file_exists(path: Path | str) -> bool:
    return Path(path).is_file()


def directory_exists(path: Path | str) -> bool:
    return Path(path).is_dir()


def ensure_directory(path: Path | str) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_files(
    directory: Path | str,
    extension: str | None = None,
) -> list[Path]:
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
    return [
        path.name
        for path in list_files(directory, extension)
    ]


def get_file_extension(path: Path | str) -> str:
    return Path(path).suffix.lower()


def get_filename_without_extension(path: Path | str) -> str:
    return Path(path).stem


def get_file_size(path: Path | str) -> int:
    return Path(path).stat().st_size


def get_file_modified_time(path: Path | str):
    return Path(path).stat().st_mtime


def delete_file(path: Path | str) -> bool:
    file_path = Path(path)

    if not file_path.is_file():
        return False

    file_path.unlink()
    return True


def find_files_by_extensions(
    directory: Path | str,
    extensions: Iterable[str],
) -> list[Path]:
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
