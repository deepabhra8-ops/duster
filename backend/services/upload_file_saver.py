from __future__ import annotations

from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

from core.storage_layout import get_upload_dir, get_upload_file_path
from core.config import MAX_UPLOAD_SIZE_BYTES, UPLOAD_ALLOWED_EXTENSIONS
from common.files.file_signature import sniff_mismatch
from common.files.file_utils import ensure_directory
from utils.logger import get_logger


logger = get_logger(__name__)


class UploadFileSaver:
    async def save(
        self,
        file: Any,
        kind: str,
    ) -> dict[str, str]:
        original_filename = self._get_filename(file)

        filename = self._sanitize_filename(
            original_filename
        )

        self._validate_extension(
            kind=kind,
            filename=filename,
        )

        upload_dir = self._prepare_upload_directory(
            kind
        )

        destination = self._build_safe_destination(
            kind=kind,
            filename=filename,
            upload_dir=upload_dir,
        )

        try:
            await self._reset_file_position(file)

            file_object = self._get_file_object(file)

            self._sniff_content(
                file_object=file_object,
                filename=filename,
            )

            self._write_file(
                file_object=file_object,
                destination=destination,
            )
            location = str(destination)

        except Exception:
            logger.exception(
                "Failed to save uploaded file: "
                "kind='%s', filename='%s'",
                kind,
                filename,
            )
            raise

        logger.info(
            "File uploaded successfully: kind='%s', filename='%s'",
            kind,
            filename,
        )

        return {
            "filename": filename,
            "location": location,
        }

    @staticmethod
    def _get_filename(
        file: Any,
    ) -> str:
        filename = str(
            getattr(
                file,
                "filename",
                "",
            )
            or ""
        ).strip()

        if not filename:
            logger.warning(
                "Upload rejected because no filename was provided"
            )
            raise ValueError(
                "Invalid filename"
            )

        return filename

    @staticmethod
    def _sanitize_filename(
        original_filename: str,
    ) -> str:
        import uuid

        filename = secure_filename(
            original_filename
        )

        if not filename:
            logger.warning(
                "Upload rejected because filename '%s' "
                "became empty after sanitization",
                original_filename,
            )
            raise ValueError(
                "Invalid filename"
            )

        return f"{uuid.uuid4().hex}_{filename}"

    @staticmethod
    def _validate_extension(
        kind: str,
        filename: str,
    ) -> None:
        allowed = UPLOAD_ALLOWED_EXTENSIONS.get(
            kind,
            (),
        )

        suffix = Path(filename).suffix.lower()

        if suffix not in allowed:
            logger.warning(
                "Upload rejected: unsupported extension '%s' "
                "for kind='%s', filename='%s'",
                suffix,
                kind,
                filename,
            )

            raise ValueError(
                f"Unsupported file type '{suffix or 'unknown'}' "
                f"for {kind}. Allowed: {', '.join(allowed)}"
            )

    @staticmethod
    def _prepare_upload_directory(
        kind: str,
    ) -> Path:
        try:
            upload_dir = get_upload_dir(
                kind
            )

            ensure_directory(
                upload_dir
            )

            return upload_dir

        except Exception:
            logger.exception(
                "Failed to prepare upload directory "
                "for kind='%s'",
                kind,
            )
            raise

    @staticmethod
    def _build_safe_destination(
        kind: str,
        filename: str,
        upload_dir: Path,
    ) -> Path:
        destination = get_upload_file_path(
            kind,
            filename,
        )

        resolved_directory = (
            upload_dir.resolve()
        )

        resolved_destination = (
            destination.resolve()
        )

        try:
            resolved_destination.relative_to(
                resolved_directory
            )
        except ValueError as exc:
            logger.error(
                "Blocked upload path outside upload directory: "
                "kind='%s', filename='%s', destination='%s'",
                kind,
                filename,
                destination,
            )

            raise ValueError(
                "Invalid upload path"
            ) from exc

        return destination

    @staticmethod
    async def _reset_file_position(
        file: Any,
    ) -> None:
        seek = getattr(
            file,
            "seek",
            None,
        )

        if seek is None:
            raise ValueError(
                "Uploaded file does not support seek"
            )

        await seek(0)

    @staticmethod
    def _get_file_object(
        file: Any,
    ) -> Any:
        file_object = getattr(
            file,
            "file",
            None,
        )

        if file_object is None:
            raise ValueError(
                "Uploaded file does not contain a file stream"
            )

        return file_object

    @staticmethod
    def _sniff_content(
        file_object: Any,
        filename: str,
    ) -> None:
        header = file_object.read(4096)
        file_object.seek(0)

        reason = sniff_mismatch(
            Path(filename).suffix.lower(),
            header,
        )

        if reason:
            logger.warning(
                "Upload rejected: filename='%s', reason='%s'",
                filename,
                reason,
            )
            raise ValueError(reason)

    @staticmethod
    def _write_file(
        file_object: Any,
        destination: Path,
        max_bytes: int = MAX_UPLOAD_SIZE_BYTES,
    ) -> None:
        chunk_size = 1024 * 1024
        written = 0

        try:
            with destination.open(
                "wb"
            ) as output_file:
                while True:
                    chunk = file_object.read(chunk_size)

                    if not chunk:
                        break

                    written += len(chunk)

                    if written > max_bytes:
                        raise ValueError(
                            f"File exceeds the {max_bytes // (1024 * 1024)} MB limit"
                        )

                    output_file.write(chunk)

        except Exception:
            destination.unlink(missing_ok=True)
            raise
