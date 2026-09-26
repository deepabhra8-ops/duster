from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
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
    __tablename__ = "saved_connections"

    id                           = Column(String(32), primary_key=True)
    name                         = Column(String(255), nullable=False)
    db_type                      = Column(String(50), nullable=False)
    description                  = Column(Text)
    connection_details_encrypted = Column(Text, nullable=False)
    created_by                   = Column(String(255))
    created_at                   = Column(DateTime, nullable=False, server_default=func.now())
    updated_at                   = Column(DateTime, nullable=False, server_default=func.now())

    last_tested_at               = Column(DateTime)
    last_test_status             = Column(String(20), nullable=False, default="unknown")
    last_test_error              = Column(Text)
    schema_count                 = Column(Integer)
    table_count                  = Column(Integer)
    last_rotated_at              = Column(DateTime)
    rotation_reminded_at         = Column(DateTime)


class IngestionConfig(Base):
    __tablename__ = "ingestion_configs"

    connection_id        = Column(
        String(32),
        ForeignKey("saved_connections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    system_type          = Column(String(20), nullable=False)
    latency_requirement  = Column(String(20), nullable=False)
    scheduling_ownership = Column(String(20), nullable=False)
    ingestion_mode       = Column(String(10), nullable=False)
    created_at           = Column(DateTime, nullable=False, server_default=func.now())
    updated_at           = Column(DateTime, nullable=False, server_default=func.now())


class ProfileMapResult(Base):
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
    row_id        = Column(String(36), nullable=False)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    job_id        = Column(
        String(36),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
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
    __tablename__ = "notifications"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    username   = Column(String(255), nullable=False)
    type       = Column(String(32), nullable=False)
    title      = Column(String(200), nullable=False)
    content    = Column(Text, nullable=False, default="")
    status     = Column(String(10), nullable=False, default="unread")
    link       = Column(String(500))
    created_at = Column(DateTime, nullable=False, server_default=text("SYSUTCDATETIME()"))


class DqRule(Base):
    __tablename__ = "dq_rules"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    rule_name         = Column(String(128), nullable=False)
    description       = Column(Text)
    template          = Column(String(64), nullable=False)
    dimension         = Column(String(32))
    params            = Column(JSON, nullable=False, default=dict)
    applies_to        = Column(JSON(none_as_null=True))
    null_policy       = Column(String(10), nullable=False, default="ignore")
    row_filter        = Column(Text)
    threshold_metric  = Column(String(16), nullable=False)
    threshold_op      = Column(String(2), nullable=False)
    threshold_value   = Column(Float, nullable=False)
    severity          = Column(String(8), nullable=False, default="error")
    weight            = Column(Float, nullable=False, default=1.0)
    scope_level       = Column(String(10))
    scope_catalog     = Column(String(255), nullable=False, default="*")
    scope_schema      = Column(String(255), nullable=False, default="*")
    scope_table       = Column(String(255), nullable=False, default="*")
    scope_column      = Column(String(255), nullable=False, default="*")
    scope_exclude     = Column(JSON, nullable=False, default=list)
    scope_table_types = Column(JSON, nullable=False, default=list)
    enabled           = Column(Boolean, nullable=False, default=True)
    version           = Column(Integer, nullable=False, default=1)
    last_run_id       = Column(String(36))
    last_run_at       = Column(DateTime)
    last_run_counts   = Column(JSON(none_as_null=True))
    created_by        = Column(String(255))
    updated_by        = Column(String(255))
    created_at        = Column(DateTime, nullable=False, server_default=text("SYSUTCDATETIME()"))
    updated_at        = Column(DateTime, nullable=False, server_default=text("SYSUTCDATETIME()"))


class DqRun(Base):
    __tablename__ = "dq_runs"

    run_id              = Column(String(36), primary_key=True)
    status              = Column(String(12), nullable=False, default="queued")
    requested_by        = Column(String(255))
    rule_ids            = Column(JSON(none_as_null=True))
    scope_override      = Column(JSON(none_as_null=True))
    where_clause        = Column(Text)
    sample_fraction     = Column(Float)
    max_parallel_tables = Column(Integer, nullable=False, default=4)
    rule_count          = Column(Integer, nullable=False, default=0)
    table_count         = Column(Integer, nullable=False, default=0)
    result_count        = Column(Integer, nullable=False, default=0)
    progress_current    = Column(Integer, nullable=False, default=0)
    progress_total      = Column(Integer, nullable=False, default=0)
    error_message       = Column(Text)
    engine_version      = Column(String(16))
    created_at          = Column(DateTime, nullable=False, server_default=text("SYSUTCDATETIME()"))
    started_at          = Column(DateTime)
    completed_at        = Column(DateTime)
    duration_ms         = Column(BigInteger)


class DqResult(Base):
    __tablename__ = "dq_results"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id           = Column(
        String(36),
        ForeignKey("dq_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id          = Column(String(16), nullable=False)
    rule_name        = Column(String(128), nullable=False)
    rule_version     = Column(Integer)
    template         = Column(String(64), nullable=False)
    dimension        = Column(String(32))
    rule_level       = Column(String(16), nullable=False)
    severity         = Column(String(8), nullable=False)
    weight           = Column(Float)
    catalog_name     = Column(String(255))
    schema_name      = Column(String(255))
    table_name       = Column(String(255))
    column_name      = Column(String(255))
    total_count      = Column(BigInteger)
    pass_count       = Column(BigInteger)
    fail_count       = Column(BigInteger)
    metric_value     = Column(Float)
    threshold_metric = Column(String(16), nullable=False)
    threshold_op     = Column(String(2), nullable=False)
    threshold_value  = Column(Float, nullable=False)
    status           = Column(String(8), nullable=False)
    message          = Column(Text)
    where_clause     = Column(Text)
    sampled          = Column(Boolean, nullable=False, default=False)
    sample_fraction  = Column(Float)
    duration_ms      = Column(BigInteger)
