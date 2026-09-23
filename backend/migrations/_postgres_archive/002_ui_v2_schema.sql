BEGIN;

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
    created_by                   VARCHAR(255),
    created_at                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_conn_scan_status
        CHECK (metadata_scan_status IN ('pending', 'scanning', 'done', 'error'))
);

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

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS name                 VARCHAR(255);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description          TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS step                 VARCHAR(4);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan        JSONB;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan_status VARCHAR(20);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata_scan_error  TEXT;

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

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS chk_status;
ALTER TABLE jobs ADD CONSTRAINT chk_status CHECK (
    status IN ('draft', 'queued', 'running', 'cancelling', 'cancelled', 'done', 'error')
);

UPDATE jobs
   SET step = COALESCE(params ->> 'step', '1')
 WHERE step IS NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_owner_step_status
    ON jobs (created_by, step, status, started_at DESC);

CREATE TABLE IF NOT EXISTS profile_map_results (
    job_id      VARCHAR(36)  PRIMARY KEY REFERENCES jobs (job_id) ON DELETE CASCADE,
    rows        JSONB        NOT NULL,
    version     INTEGER      NOT NULL DEFAULT 1,
    row_count   INTEGER      NOT NULL DEFAULT 0,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by  VARCHAR(255)
);

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

CREATE TABLE IF NOT EXISTS validation_results (
    job_id        VARCHAR(36) PRIMARY KEY REFERENCES jobs (job_id) ON DELETE CASCADE,
    overall_score NUMERIC(5, 2),
    summary       JSONB     NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_validation_results_created_at
    ON validation_results (created_at DESC);

COMMIT;
