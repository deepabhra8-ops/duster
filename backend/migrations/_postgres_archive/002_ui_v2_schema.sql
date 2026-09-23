-- Migration 002: UI V2 - saved connections, draft jobs, profile-map results/edits,
-- validation results.
--
-- Every statement is idempotent so this file can be re-applied safely.
--
-- Background: the V2 UI treats profile-map rows, validation summaries, metadata scans
-- and draft jobs as durable state. Execution happens remotely on AWS Glue and the API
-- runs multiple worker processes, so none of that can live in process memory - it all
-- needs real schema, which is what this migration adds.

BEGIN;

-- ============================================================================
-- 1. Saved connections
-- ============================================================================
-- connection_details_encrypted holds a Fernet token of the whole details dict
-- (see backend/utils/crypto.py). `port` is duplicated out of that blob purely so
-- the list view can show it without decrypting every row.

CREATE TABLE IF NOT EXISTS saved_connections (
    id                           VARCHAR(32)  PRIMARY KEY,
    name                         VARCHAR(255) NOT NULL,
    db_type                      VARCHAR(50)  NOT NULL,
    description                  TEXT,
    port                         INTEGER,
    connection_details_encrypted TEXT         NOT NULL,
    metadata_scan                JSONB,
    metadata_scan_status         VARCHAR(20)  NOT NULL DEFAULT 'pending',
    metadata_scan_error          TEXT,
    metadata_scanned_at          TIMESTAMP,
    -- Nullable on purpose. An earlier build of this app created this table
    -- without recording an owner, so rows can predate ownership. Those legacy
    -- rows are usable by everyone and manageable only by an admin (enforced in
    -- SavedConnectionService._require_owner) rather than being backfilled with
    -- an invented owner or left permanently unmanageable.
    created_by                   VARCHAR(255),
    created_at                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_conn_scan_status
        CHECK (metadata_scan_status IN ('pending', 'scanning', 'done', 'error'))
);

-- Bring a table created by that earlier build up to the shape above. All no-ops
-- on a database where the CREATE above just ran.
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS description         TEXT;
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS port                INTEGER;
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS metadata_scan_error TEXT;
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS metadata_scanned_at TIMESTAMP;
ALTER TABLE saved_connections
    ADD COLUMN IF NOT EXISTS metadata_scan_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE saved_connections
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    -- That earlier build stored metadata_scan as JSON-encoded TEXT. This app
    -- reads and writes it as JSONB, so an unconverted column would fail at
    -- runtime rather than at migration time. The CASE guards empty/invalid
    -- values so one bad row can't abort the conversion.
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'saved_connections'
           AND column_name = 'metadata_scan'
           AND data_type <> 'jsonb'
    ) THEN
        ALTER TABLE saved_connections
            ALTER COLUMN metadata_scan TYPE JSONB
            USING CASE
                WHEN metadata_scan IS NULL OR btrim(metadata_scan) = '' THEN NULL
                ELSE metadata_scan::jsonb
            END;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_conn_scan_status'
    ) THEN
        ALTER TABLE saved_connections
            ADD CONSTRAINT chk_conn_scan_status
            CHECK (metadata_scan_status IN ('pending', 'scanning', 'done', 'error'));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_saved_connections_name
    ON saved_connections (lower(name));

CREATE INDEX IF NOT EXISTS idx_saved_connections_created_at
    ON saved_connections (created_at DESC);


-- ============================================================================
-- 2. Jobs: new columns + widened status vocabulary
-- ============================================================================

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS name                 VARCHAR(255);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description          TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS step                 VARCHAR(4);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan        JSONB;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan_status VARCHAR(20);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan_error  TEXT;

-- Deleting a connection must not delete job history, hence SET NULL.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS connection_id VARCHAR(32);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_job_id VARCHAR(36);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_connection_id'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT fk_jobs_connection_id
            FOREIGN KEY (connection_id) REFERENCES saved_connections (id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_source_job_id'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT fk_jobs_source_job_id
            FOREIGN KEY (source_job_id) REFERENCES jobs (job_id)
            ON DELETE SET NULL;
    END IF;
END
$$;

-- Fixes a live bug as a side effect: JobService.request_cancel and
-- PipelineService._poll_glue_status already write status='cancelled', which the
-- original CHECK rejected - every cancel raised against a migrated database.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS chk_status;
ALTER TABLE jobs ADD CONSTRAINT chk_status CHECK (
    status IN ('draft', 'queued', 'running', 'cancelling', 'cancelled', 'done', 'error')
);

-- Backfill `step` for pre-existing rows from the params blob.
UPDATE jobs
   SET step = COALESCE(params ->> 'step', '1')
 WHERE step IS NULL;

-- Serves the V2 jobs list, which filters by step+status per owner and polls every 1.4s.
CREATE INDEX IF NOT EXISTS idx_jobs_owner_step_status
    ON jobs (created_by, step, status, started_at DESC);


-- ============================================================================
-- 3. Profile-map results
-- ============================================================================
-- One row per job. Deliberately NOT a column on `jobs`: the rows blob can reach
-- a few MB on a wide source, and the jobs list endpoint is polled every 1.4s.
-- `version` drives the optimistic-concurrency 409 on concurrent edits.

CREATE TABLE IF NOT EXISTS profile_map_results (
    job_id      VARCHAR(36)  PRIMARY KEY REFERENCES jobs (job_id) ON DELETE CASCADE,
    rows        JSONB        NOT NULL,
    version     INTEGER      NOT NULL DEFAULT 1,
    row_count   INTEGER      NOT NULL DEFAULT 0,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by  VARCHAR(255)
);


-- ============================================================================
-- 4. Profile-map edit audit
-- ============================================================================
-- These edits decide which DQ rules run against production data, so who changed
-- what is recorded per cell. Written in the same transaction as the version bump.

CREATE TABLE IF NOT EXISTS profile_map_edits (
    id            BIGSERIAL    PRIMARY KEY,
    job_id        VARCHAR(36)  NOT NULL REFERENCES jobs (job_id) ON DELETE CASCADE,
    table_name    VARCHAR(255) NOT NULL,
    column_name   VARCHAR(255) NOT NULL,
    field         VARCHAR(64)  NOT NULL,
    old_value     TEXT,
    new_value     TEXT,
    version_after INTEGER      NOT NULL,
    edited_by     VARCHAR(255) NOT NULL,
    edited_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_profile_map_edits_job
    ON profile_map_edits (job_id, edited_at DESC);


-- ============================================================================
-- 5. Validation results
-- ============================================================================
-- overall_score is a real column, not buried in the JSON, so the dashboard can
-- trend it without unpacking every summary.

CREATE TABLE IF NOT EXISTS validation_results (
    job_id        VARCHAR(36) PRIMARY KEY REFERENCES jobs (job_id) ON DELETE CASCADE,
    overall_score NUMERIC(5, 2),
    summary       JSONB     NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_validation_results_created_at
    ON validation_results (created_at DESC);

COMMIT;
