"""SQLAlchemy ORM models for the application.

Mirrors backend/migrations/*.sql - the migrations are the source of truth and are
applied manually; nothing here calls create_all().
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.mssql import JSON

from core.db import Base


class Job(Base):
    __tablename__ = "jobs"

    job_id            = Column(String(36), primary_key=True)
    status            = Column(String(20), nullable=False, default="queued")
    params            = Column(JSON)
    log               = Column(JSON, default=list)
    report_path       = Column(Text)
    profile_path      = Column(Text)
    staging_path      = Column(Text)
    progress_current  = Column(Integer, default=0)
    progress_total    = Column(Integer, default=0)
    glue_job_run_id   = Column(String(100))
    started_at        = Column(DateTime, server_default=func.now())
    completed_at      = Column(DateTime)
    created_by        = Column(String(255))
    error_message     = Column(Text)

    # ── V2 ──────────────────────────────────────────────────────────────
    name                 = Column(String(255))
    description          = Column(Text)
    step                 = Column(String(4))
    connection_id        = Column(
        String(32),
        ForeignKey("saved_connections.id", ondelete="SET NULL"),
    )
    source_job_id        = Column(
        String(36),
        ForeignKey("jobs.job_id", ondelete="SET NULL"),
    )


class SavedConnection(Base):
    """A reusable database connection. Credentials are stored as a single Fernet
    token in connection_details_encrypted (see common/security/crypto.py); `port` is
    duplicated out of that blob so the list view needn't decrypt every row."""

    __tablename__ = "saved_connections"

    id                           = Column(String(32), primary_key=True)
    name                         = Column(String(255), nullable=False)
    db_type                      = Column(String(50), nullable=False)
    description                  = Column(Text)
    connection_details_encrypted = Column(Text, nullable=False)
    # No catalog cache lives here. Schemas, tables and columns are all read live
    # from the source per selection (metadata_scan_service) - see migration 007
    # for why the schema-name cache that used to sit here was removed.
    # Nullable: rows created by an earlier build predate ownership. See the
    # migration and SavedConnectionService._require_owner for how those are treated.
    created_by                   = Column(String(255))
    created_at                   = Column(DateTime, nullable=False, server_default=func.now())
    updated_at                   = Column(DateTime, nullable=False, server_default=func.now())


class ProfileMapResult(Base):
    """Profile-map rows for one job, plus the version counter that drives
    optimistic-concurrency conflict detection on concurrent edits."""

    __tablename__ = "profile_map_results"

    job_id     = Column(
        String(36),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    rows       = Column(JSON, nullable=False)
    version    = Column(Integer, nullable=False, default=1)
    row_count  = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_by = Column(String(255))
    failed_tables = Column(JSON, nullable=False, default=list)


class ProfileMapEdit(Base):
    """Audit row: one per profile-map cell changed."""

    __tablename__ = "profile_map_edits"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id        = Column(
        String(36),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name    = Column(String(255), nullable=False)
    column_name   = Column(String(255), nullable=False)
    field         = Column(String(64), nullable=False)
    old_value     = Column(Text)
    new_value     = Column(Text)
    version_after = Column(Integer, nullable=False)
    edited_by     = Column(String(255), nullable=False)
    edited_at     = Column(DateTime, nullable=False, server_default=func.now())
    # Python-generated (str(uuid.uuid4())), never DB-generated - see
    # engine/profile_map/normalize_rows.py and services/profile_map_service.py.
    row_id        = Column(String(36), nullable=False)


class ValidationResult(Base):
    """Stored DQ summary for a validator job. overall_score is a real column so
    the dashboard can trend it without unpacking the JSON."""

    __tablename__ = "validation_results"

    job_id        = Column(
        String(36),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # A 0..1 fraction at build_summary's 4-decimal precision, not a percentage -
    # see migration 004, which widened this from NUMERIC(5,2).
    overall_score = Column(Numeric(6, 4))
    summary       = Column(JSON, nullable=False)
    created_at    = Column(DateTime, nullable=False, server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    session_id   = Column(String(64), primary_key=True)
    username     = Column(String(255), nullable=False)
    expires_at   = Column(DateTime, nullable=False)
    created_at   = Column(DateTime, server_default=func.now())


class Notification(Base):
    """An in-app notification, shown under the top bar's bell.

    Keyed by `username`, the app's only identity handle (see migration 008). Rows
    are written by the API and by a trigger on `jobs` when a job finishes, and only
    ever change in one way: status unread -> read.
    """

    __tablename__ = "notifications"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    username   = Column(String(255), nullable=False)
    type       = Column(String(32), nullable=False)
    title      = Column(String(200), nullable=False)
    content    = Column(Text, nullable=False, default="")
    status     = Column(String(10), nullable=False, default="unread")
    link       = Column(String(500))
    created_at = Column(DateTime, nullable=False, server_default=text("SYSUTCDATETIME()"))
