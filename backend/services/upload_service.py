"""Coordinates upload validation, persistence, listing, and preview by delegating to the upload helper classes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.storage_layout import (
    ensure_directories,
    get_upload_file_path,
)
from core.config import UPLOAD_KINDS
from services.upload_archive_policy import UploadArchivePolicy
from services.upload_file_lister import UploadFileLister
from services.upload_file_saver import UploadFileSaver
from services.upload_preview_reader import UploadPreviewReader
from common.files.file_utils import file_exists
from utils.logger import get_logger, log_and_reraise


logger = get_logger(__name__)


class UploadService:
    """Orchestrates upload saving, listing, and preview for the routes layer."""

    @log_and_reraise(logger, "Failed to initialize upload service")
    def __init__(
        self,
        file_saver: UploadFileSaver | None = None,
        file_lister: UploadFileLister | None = None,
        archive_policy: UploadArchivePolicy | None = None,
        preview_reader: UploadPreviewReader | None = None,
    ) -> None:
        """Wire up upload collaborators and ensure upload directories exist."""
        self.file_saver = (
            file_saver
            or UploadFileSaver()
        )
        self.file_lister = (
            file_lister
            or UploadFileLister()
        )
        self.archive_policy = (
            archive_policy
            or UploadArchivePolicy()
        )
        self.preview_reader = (
            preview_reader
            or UploadPreviewReader()
        )

        ensure_directories()
        logger.debug(
            "Initialized upload service"
        )

    async def save_files(
        self,
        files: list[Any],
        kind: str = "data",
    ) -> dict[str, Any]:
        """Validate and save a batch of uploaded files, returning results per file."""
        validation_error = self._validate_upload_request(
            files=files,
            kind=kind,
        )

        if validation_error:
            return validation_error

        valid_files = self._get_valid_files(files)

        if not valid_files:
            logger.warning(
                "No files provided for upload kind '%s'",
                kind,
            )
            return {
                "ok": False,
                "error": "No file(s) provided",
            }

        logger.info(
            "Processing upload: kind='%s', file_count=%d",
            kind,
            len(valid_files),
        )

        uploaded: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []

        for file in valid_files:
            result = await self._save_single_file(
                file=file,
                kind=kind,
            )

            if result["ok"]:
                uploaded.append(
                    result["file"]
                )
            else:
                errors.append(
                    result["error"]
                )

        return self._build_upload_result(
            kind=kind,
            uploaded=uploaded,
            errors=errors,
        )

    def list_uploads(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str = "",
        file_type: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """List uploaded files with archive status applied, then filtered, sorted, and paginated."""
        files = self.file_lister.list_all()

        files = self.archive_policy.apply(
            files
        )

        filtered_files = self.file_lister.filter(
            files=files,
            search=search,
            file_type=file_type,
            include_archived=include_archived,
        )

        sorted_files = self.file_lister.sort(
            files=filtered_files,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        (
            page_items,
            total,
            total_pages,
        ) = self.file_lister.paginate(
            files=sorted_files,
            page=page,
            page_size=page_size,
        )

        simple_files = (
            self.file_lister.get_simple_file_lists()
        )

        result = {
            **simple_files,
            "files": page_items,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": total_pages,
        }

        logger.debug(
            "Listed uploads: page=%s, total=%s",
            page,
            total,
        )

        return result

    def preview_file(
        self,
        kind: str = "data",
        filename: str = "",
        rows: int = 50,
    ) -> dict[str, Any]:
        """Return a preview of an uploaded CSV or Excel file."""
        validation_error = self._validate_preview_request(
            kind=kind,
            filename=filename,
        )

        if validation_error:
            return validation_error

        try:
            file_path = self.get_upload_path(
                kind=kind,
                filename=filename,
            )
        except ValueError as exc:
            logger.warning(
                "Invalid preview path for '%s': %s",
                filename,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
            }

        if not file_exists(file_path):
            logger.warning(
                "Preview file not found: '%s'",
                file_path,
            )
            return {
                "ok": False,
                "error": "File not found",
            }

        try:
            preview = self.preview_reader.read(
                file_path=file_path,
                rows=rows,
            )

            return {
                "ok": True,
                **preview,
            }

        except FileNotFoundError:
            logger.warning(
                "Preview file not found: '%s'",
                file_path,
            )
            return {
                "ok": False,
                "error": "File not found",
            }

        except ValueError as exc:
            logger.warning(
                "Invalid preview request for '%s': %s",
                filename,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
            }

        except Exception as exc:
            logger.exception(
                "Failed to preview upload '%s'",
                filename,
            )
            return {
                "ok": False,
                "error": str(exc),
            }

    def get_upload_path(
        self,
        kind: str,
        filename: str,
    ) -> Path:
        """Resolve the filesystem path for an uploaded file."""
        self._validate_upload_kind(kind)

        path = get_upload_file_path(
            kind,
            filename,
        )

        logger.debug(
            "Resolved upload path: "
            "kind='%s', filename='%s', path='%s'",
            kind,
            filename,
            path,
        )

        return path

    @staticmethod
    def _validate_upload_request(
        files: list[Any],
        kind: str,
    ) -> dict[str, Any] | None:
        """Return an error payload if the upload kind or file list is invalid."""
        if kind not in UPLOAD_KINDS:
            logger.warning(
                "Unsupported upload kind '%s'",
                kind,
            )
            return {
                "ok": False,
                "error": f"Unsupported upload kind: {kind}",
            }

        if not files:
            return {
                "ok": False,
                "error": "No file(s) provided",
            }

        return None

    @staticmethod
    def _get_valid_files(
        files: list[Any],
    ) -> list[Any]:
        """Return only files that carry a filename."""
        return [
            file
            for file in files
            if getattr(
                file,
                "filename",
                "",
            )
        ]

    async def _save_single_file(
        self,
        file: Any,
        kind: str,
    ) -> dict[str, Any]:
        """Save one uploaded file, returning its result or error."""
        original_filename = str(
            getattr(
                file,
                "filename",
                "",
            )
        )

        try:
            saved_file = await self.file_saver.save(
                file=file,
                kind=kind,
            )

            return {
                "ok": True,
                "file": saved_file,
            }

        except ValueError as exc:
            logger.warning(
                "Upload rejected: "
                "kind='%s', filename='%s', reason='%s'",
                kind,
                original_filename,
                exc,
            )

            return {
                "ok": False,
                "error": {
                    "filename": original_filename,
                    "error": str(exc),
                },
            }

        except Exception:
            logger.exception(
                "Failed to save uploaded file: "
                "kind='%s', filename='%s'",
                kind,
                original_filename,
            )

            return {
                "ok": False,
                "error": {
                    "filename": original_filename,
                    "error": "Failed to save file",
                },
            }

    @staticmethod
    def _build_upload_result(
        kind: str,
        uploaded: list[dict[str, str]],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build the aggregate result payload for a batch upload."""
        if errors and not uploaded:
            logger.warning(
                "All uploads failed for kind '%s'",
                kind,
            )

            return {
                "ok": False,
                "error": "All uploads failed",
                "details": errors,
            }

        result = {
            "ok": True,
            "uploaded": uploaded,
            "errors": errors,
            "filename": (
                uploaded[0]["filename"]
                if uploaded
                else ""
            ),
            # Where the file actually landed: an S3 key or a local path, depending on
            # how the saver stored it. Reported for diagnostics only - callers that
            # need to find the file again go by `filename`, which is stable across
            # both storage modes.
            "path": (
                uploaded[0]["location"]
                if uploaded
                else ""
            ),
        }

        logger.info(
            "Upload processing completed: "
            "kind='%s', uploaded_count=%d, error_count=%d",
            kind,
            len(uploaded),
            len(errors),
        )

        return result

    @staticmethod
    def _validate_upload_kind(
        kind: str,
    ) -> None:
        """Raise if the upload kind is unsupported."""
        if kind not in UPLOAD_KINDS:
            logger.warning(
                "Unsupported upload kind '%s'",
                kind,
            )
            raise ValueError(
                f"Unsupported upload kind: {kind}"
            )

    @staticmethod
    def _validate_preview_request(
        kind: str,
        filename: str,
    ) -> dict[str, Any] | None:
        """Return an error payload if the preview request is invalid."""
        if not filename:
            logger.warning(
                "Preview requested without a filename"
            )
            return {
                "ok": False,
                "error": "filename required",
            }

        if kind not in UPLOAD_KINDS:
            logger.warning(
                "Unsupported preview upload kind '%s'",
                kind,
            )
            return {
                "ok": False,
                "error": f"Unsupported upload kind: {kind}",
            }

        return None


upload_service = UploadService()
