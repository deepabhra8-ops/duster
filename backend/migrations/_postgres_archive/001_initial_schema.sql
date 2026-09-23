-- Migration 001: Initial Schema for Data Quality Validator

-- Users table is expected to exist and be managed externally, but here is a reference:
-- CREATE TABLE users (
--     user_id SERIAL PRIMARY KEY,
--     user_name VARCHAR(255) UNIQUE NOT NULL,
--     password_hash VARCHAR(255) NOT NULL,
--     is_active BOOLEAN DEFAULT TRUE,
--     is_admin BOOLEAN DEFAULT FALSE,
--     expiry_date DATE,
--     user_email_id VARCHAR(255),
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS jobs (
    job_id VARCHAR(36) PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    params JSONB,
    log JSONB DEFAULT '[]'::jsonb,
    report_path TEXT,
    profile_path TEXT,
    staging_path TEXT,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    glue_job_run_id VARCHAR(100),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(255),
    error_message TEXT,
    CONSTRAINT chk_status CHECK (status IN ('queued', 'running', 'done', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_started_at ON jobs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);

CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
