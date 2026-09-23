"""Filesystem path helpers for job, upload, staging, and report locations used across the backend."""

from pathlib import Path

from core.config import (
    JOBS_DIR,
    UPLOADS_DIR,
    DATA_UPLOADS_DIR,
    LOV_UPLOADS_DIR,
    PROFILE_MAP_UPLOADS_DIR,
    UPLOAD_KINDS,
    PROFILE_MAP_EXTENSIONS,
)


def ensure_directories() -> None:
    """Create required application directories."""

    JOBS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    UPLOADS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for upload_dir in (
        DATA_UPLOADS_DIR,
        LOV_UPLOADS_DIR,
        PROFILE_MAP_UPLOADS_DIR,
    ):
        upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


def get_job_dir(job_id: str) -> Path:
    """Return the directory for a specific job."""

    return JOBS_DIR / job_id


def get_job_config_path(job_id: str) -> Path:
    """Return the DQ configuration file path for a job."""

    return get_job_dir(job_id) / "dq_parameter.yaml"


def get_staging_dir(job_id: str) -> Path:
    """Return the staging directory for a job."""

    return get_job_dir(job_id) / "staging"


def get_reports_dir(job_id: str) -> Path:
    """Return the reports directory for a job."""

    return get_job_dir(job_id) / "reports"


def get_profile_map_job_path(job_id: str) -> Path:
    """Return the profile map path generated for a job."""

    return (
        get_job_dir(job_id)
        / f"Source_DQ_Profile_Map_{job_id}.xlsx"
    )


def get_report_job_path(job_id: str) -> Path:
    """Return the DQ validation report path generated for a job."""

    return (
        get_reports_dir(job_id)
        / f"DQ-Validation-Report_{job_id}.xlsx"
    )


def get_upload_dir(kind: str) -> Path:
    """Return the upload directory for a supported upload kind."""

    upload_dirs = {
        "data": DATA_UPLOADS_DIR,
        "lov": LOV_UPLOADS_DIR,
        "profile_map": PROFILE_MAP_UPLOADS_DIR,
    }

    if kind not in upload_dirs:
        raise ValueError(
            f"Unsupported upload kind: {kind}. "
            f"Supported kinds: {', '.join(UPLOAD_KINDS)}"
        )

    return upload_dirs[kind]


def get_upload_file_path(
    kind: str,
    filename: str,
) -> Path:
    """Return a safe path inside an upload directory, rejecting any filename that would resolve outside it."""

    upload_dir = get_upload_dir(kind).resolve()

    file_path = (
        upload_dir / filename
    ).resolve()

    if upload_dir not in file_path.parents:
        raise ValueError(
            "Invalid upload path"
        )

    return file_path


def get_profile_map_upload_path(
    filename: str,
) -> Path:
    """Return the validated path for an uploaded profile map, rejecting unsupported extensions."""

    path = get_upload_file_path(
        "profile_map",
        filename,
    )

    if path.suffix.lower() not in PROFILE_MAP_EXTENSIONS:
        raise ValueError(
            f"Unsupported profile map format: {path.suffix}"
        )

    return path


def get_lov_upload_dir() -> Path:
    """Return the LOV upload directory."""

    return LOV_UPLOADS_DIR


def get_data_upload_dir() -> Path:
    """Return the data upload directory."""

    return DATA_UPLOADS_DIR


def get_profile_map_upload_dir() -> Path:
    """Return the profile map upload directory."""

    return PROFILE_MAP_UPLOADS_DIR


def ensure_job_directory(
    job_id: str,
) -> Path:
    """Create and return a job directory."""

    job_dir = get_job_dir(job_id)

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return job_dir


def ensure_staging_directory(
    job_id: str,
) -> Path:
    """Create and return a job staging directory."""

    staging_dir = get_staging_dir(job_id)

    staging_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return staging_dir


def ensure_reports_directory(
    job_id: str,
) -> Path:
    """Create and return a job reports directory."""

    reports_dir = get_reports_dir(job_id)

    reports_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return reports_dir
