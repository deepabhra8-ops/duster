"""Discovers, filters, sorts, and paginates uploaded file metadata for UploadService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from core.storage_layout import get_upload_dir
from core.config import UPLOAD_KIND_LABELS, UPLOAD_KINDS
from common.files.file_utils import (
    ensure_directory,
    list_files,
)
from utils.logger import get_logger


logger = get_logger(__name__)


class UploadFileLister:
    """Discover, filter, sort, and paginate uploaded files."""

    def list_all(self) -> list[dict[str, Any]]:
        """Return metadata for all uploaded files across every upload kind."""
        try:
            files = []

            for kind in UPLOAD_KINDS:
                files.extend(
                    self._list_kind_files(kind)
                )

            logger.debug(
                "Discovered %d uploaded files",
                len(files),
            )

            return files
        except Exception:
            logger.exception("Failed to list uploaded files")
            raise

    def list_kind(
        self,
        kind: str,
    ) -> list[dict[str, Any]]:
        """Return uploaded-file metadata for one upload kind."""
        try:
            self._validate_kind(kind)
            result = self._list_kind_files(kind)
            logger.debug(
                "Discovered %d uploaded files for kind '%s'",
                len(result),
                kind,
            )
            return result
        except Exception:
            logger.exception("Failed to list uploads for kind '%s'", kind)
            raise

    def filter(
        self,
        files: Iterable[dict[str, Any]],
        search: str = "",
        file_type: str = "",
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Filter uploaded files by type, filename search, and archive status."""
        try:
            filtered = list(files)

            if file_type:
                filtered = self._filter_by_type(
                    filtered,
                    file_type,
                )

            search_term = search.strip().lower()

            if search_term:
                filtered = self._filter_by_search(
                    filtered,
                    search_term,
                )

            elif not include_archived:
                filtered = self._exclude_archived(
                    filtered
                )

            logger.debug(
                "Filtered uploads: "
                "search='%s', file_type='%s', "
                "include_archived=%s, result_count=%d",
                search,
                file_type,
                include_archived,
                len(filtered),
            )

            return filtered
        except Exception:
            logger.exception("Failed to filter uploads")
            raise

    def sort(
        self,
        files: Iterable[dict[str, Any]],
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Sort uploaded files by filename or created_at."""
        try:
            self._validate_sort_options(
                sort_by=sort_by,
                sort_order=sort_order,
            )

            reverse = sort_order == "desc"

            key_function = self._get_sort_key(
                sort_by
            )

            sorted_files = sorted(
                files,
                key=key_function,
                reverse=reverse,
            )

            logger.debug(
                "Sorted uploads: sort_by='%s', sort_order='%s'",
                sort_by,
                sort_order,
            )

            return sorted_files
        except Exception:
            logger.exception("Failed to sort uploads")
            raise

    @staticmethod
    def paginate(
        files: list[dict[str, Any]],
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Return one page of already-filtered and sorted files."""
        try:
            if page < 1:
                raise ValueError(
                    "Page must be greater than or equal to 1"
                )

            if page_size < 1:
                raise ValueError(
                    "Page size must be greater than or equal to 1"
                )

            total = len(files)

            start = (page - 1) * page_size
            end = start + page_size

            page_items = files[start:end]

            total_pages = (
                (total + page_size - 1) // page_size
                if total
                else 0
            )

            logger.debug(
                "Paginated uploads: page=%s, page_size=%s, total=%s",
                page,
                page_size,
                total,
            )
            return (
                page_items,
                total,
                total_pages,
            )
        except Exception:
            logger.exception("Failed to paginate uploads")
            raise

    def get_simple_file_lists(
        self,
    ) -> dict[str, list[str]]:
        """Return sorted filename lists grouped by upload kind."""
        try:
            simple_files = {}

            for kind in UPLOAD_KINDS:
                simple_files[kind] = self._get_filenames_for_kind(
                    kind
                )

            logger.debug("Built simple upload filename lists")
            return simple_files
        except Exception:
            logger.exception("Failed to build simple upload filename lists")
            raise

    def list_and_paginate(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str = "",
        file_type: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """List uploads through discovery, filtering, sorting, and pagination in one call."""
        try:
            files = self.list_all()

            files = self.filter(
                files=files,
                search=search,
                file_type=file_type,
                include_archived=include_archived,
            )

            files = self.sort(
                files=files,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            (
                page_items,
                total,
                total_pages,
            ) = self.paginate(
                files=files,
                page=page,
                page_size=page_size,
            )

            result = {
                "files": page_items,
                "total": total,
                "page": page,
                "pageSize": page_size,
                "totalPages": total_pages,
            }
            logger.info(
                "Listed and paginated uploads: page=%s, total=%s",
                page,
                total,
            )
            return result
        except Exception:
            logger.exception("Failed to list and paginate uploads")
            raise

    @staticmethod
    def _list_kind_files(
        kind: str,
    ) -> list[dict[str, Any]]:
        """Discover files belonging to one upload kind."""
        upload_dir = ensure_directory(
            get_upload_dir(kind)
        )

        files = []

        for path in list_files(upload_dir):
            metadata = UploadFileLister._build_file_metadata(
                path=path,
                kind=kind,
            )

            if metadata is not None:
                files.append(metadata)

        return files

    @staticmethod
    def _build_file_metadata(
        path: Any,
        kind: str,
    ) -> dict[str, Any] | None:
        """Build metadata for a single uploaded file."""
        try:
            stat = path.stat()

        except OSError:
            logger.warning(
                "Unable to inspect uploaded file '%s'",
                path,
                exc_info=True,
            )
            return None

        return {
            "filename": path.name,
            "kind": kind,
            "kind_label": UPLOAD_KIND_LABELS.get(
                kind,
                kind,
            ),
            "created_at": datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat(),
            "size": stat.st_size,
        }

    @staticmethod
    def _get_filenames_for_kind(
        kind: str,
    ) -> list[str]:
        """Return sorted filenames for one upload kind."""
        upload_dir = ensure_directory(
            get_upload_dir(kind)
        )

        return sorted(
            path.name
            for path in list_files(upload_dir)
        )

    @staticmethod
    def _filter_by_type(
        files: list[dict[str, Any]],
        file_type: str,
    ) -> list[dict[str, Any]]:
        """Filter files by upload kind."""
        return [
            item
            for item in files
            if item["kind"] == file_type
        ]

    @staticmethod
    def _filter_by_search(
        files: list[dict[str, Any]],
        search_term: str,
    ) -> list[dict[str, Any]]:
        """Filter files by case-insensitive filename search."""
        return [
            item
            for item in files
            if search_term in item["filename"].lower()
        ]

    @staticmethod
    def _exclude_archived(
        files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return only files that are not marked as archived."""
        return [
            item
            for item in files
            if not item.get("archived", False)
        ]

    @staticmethod
    def _get_sort_key(
        sort_by: str,
    ):
        """Return the key function for a supported sort field."""
        if sort_by == "filename":
            return lambda item: item[
                "filename"
            ].lower()

        return lambda item: item[
            "created_at"
        ]

    @staticmethod
    def _validate_kind(
        kind: str,
    ) -> None:
        """Validate an upload kind."""
        if kind not in UPLOAD_KINDS:
            raise ValueError(
                f"Unsupported upload kind: {kind}"
            )

    @staticmethod
    def _validate_sort_options(
        sort_by: str,
        sort_order: str,
    ) -> None:
        """Validate supported sorting options."""
        supported_sort_fields = {
            "filename",
            "created_at",
        }

        if sort_by not in supported_sort_fields:
            raise ValueError(
                f"Unsupported sort field: {sort_by}"
            )

        if sort_order not in {
            "asc",
            "desc",
        }:
            raise ValueError(
                f"Unsupported sort order: {sort_order}"
            )
