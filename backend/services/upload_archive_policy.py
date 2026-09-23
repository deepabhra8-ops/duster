"""Applies the active/archived policy to uploaded files based on the configured JOB_ARCHIVE_THRESHOLD."""

from __future__ import annotations

from typing import Any, Iterable

from core.config import JOB_ARCHIVE_THRESHOLD
from utils.logger import get_logger


logger = get_logger(__name__)


class UploadArchivePolicy:
    """Apply the configured active/archive policy to uploaded files."""

    def apply(
        self,
        files: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Mark the newest JOB_ARCHIVE_THRESHOLD files active and the rest archived."""
        file_list = list(files)

        self._validate_threshold()

        if not file_list:
            return []

        active_keys = self._get_active_file_keys(
            file_list
        )

        archived_files = [
            self._mark_file(
                file=item,
                archived=self._get_file_key(item)
                not in active_keys,
            )
            for item in file_list
        ]

        self._log_result(
            total=len(archived_files),
            active_count=len(active_keys),
        )

        return archived_files

    @staticmethod
    def _get_active_file_keys(
        files: list[dict[str, Any]],
    ) -> set[tuple[str, str]]:
        """Return identifiers for files that remain active."""
        sorted_files = sorted(
            files,
            key=lambda item: item["created_at"],
            reverse=True,
        )

        active_files = sorted_files[
            :JOB_ARCHIVE_THRESHOLD
        ]

        return {
            UploadArchivePolicy._get_file_key(
                item
            )
            for item in active_files
        }

    @staticmethod
    def _get_file_key(
        file: dict[str, Any],
    ) -> tuple[str, str]:
        """Return the unique identity used for archive decisions."""
        return (
            str(file.get("filename", "")),
            str(file.get("kind", "")),
        )

    @staticmethod
    def _mark_file(
        file: dict[str, Any],
        archived: bool,
    ) -> dict[str, Any]:
        """Return a copy of file metadata with archive status."""
        result = dict(file)
        result["archived"] = archived
        return result

    @staticmethod
    def _validate_threshold() -> None:
        """Validate the configured archive threshold."""
        if JOB_ARCHIVE_THRESHOLD < 1:
            raise ValueError(
                "JOB_ARCHIVE_THRESHOLD must be greater than zero"
            )

    @staticmethod
    def _log_result(
        total: int,
        active_count: int,
    ) -> None:
        """Log the archive-policy result."""
        archived_count = total - active_count

        logger.debug(
            "Applied upload archive policy: "
            "total=%d, active=%d, archived=%d, threshold=%d",
            total,
            active_count,
            archived_count,
            JOB_ARCHIVE_THRESHOLD,
        )
