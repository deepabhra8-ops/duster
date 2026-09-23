-- Migration 001: Initial schema for SQL Server (duster_db).
--
-- Consolidated, not a line-by-line port of the old Postgres migration
-- history (see backend/migrations/_postgres_archive/ for that record). This
-- database starts empty, so it gets the net final shape of all 9 Postgres
-- migrations directly, rather than replaying intermediate columns a later
-- migration only went on to drop (the schema-cache saga in 002/003/007).
--
-- JSONB has no SQL Server equivalent - JSON columns below are NVARCHAR(MAX)
-- with an ISJSON CHECK constraint. UUID has no equivalent either, but every
-- UUID this app ever stores is generated in Python (str(uuid.uuid4())), never
-- by the database, so VARCHAR(36) is a pure type-narrowing, not a behavior
-- change.

-- ============================================================================
-- 0. users
-- ============================================================================
-- Previously "externally managed" by the old company infra; nothing external
-- exists in this personal setup, so this migration now owns it. Shape mirrors
-- every column user_repository.py actually queries, plus the ones the old
-- Postgres migration's reference comment documented alongside them.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
BEGIN
    CREATE TABLE dbo.users (
        user_id       INT IDENTITY(1,1) PRIMARY KEY,
        user_name     VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        is_active     BIT NOT NULL DEFAULT 1,
        is_admin      BIT NOT NULL DEFAULT 0,
        expiry_date   DATE,
        user_email_id VARCHAR(255),
        created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        modified_at   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

-- ============================================================================
-- 1. jobs
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'jobs')
BEGIN
    CREATE TABLE dbo.jobs (
        job_id            VARCHAR(36)  NOT NULL PRIMARY KEY,
        status            VARCHAR(20)  NOT NULL DEFAULT 'queued',
        params            NVARCHAR(MAX) NULL,
        log               NVARCHAR(MAX) NULL DEFAULT '[]',
        report_path       NVARCHAR(MAX),
        profile_path      NVARCHAR(MAX),
        staging_path      NVARCHAR(MAX),
        progress_current  INT DEFAULT 0,
        progress_total    INT DEFAULT 0,
        -- Vestigial: AWS Glue is fully removed (jobs now run in-process via
        -- job_runner.py) and this is always NULL going forward, but
        -- job_repository.py still reads/serializes it. Dropping it is an
        -- application-code cleanup, out of scope for this DB port.
        glue_job_run_id   VARCHAR(100),
        started_at        DATETIME2 DEFAULT SYSUTCDATETIME(),
        completed_at      DATETIME2,
        created_by        VARCHAR(255),
        error_message     NVARCHAR(MAX),
        -- V2
        name              VARCHAR(255),
        description       NVARCHAR(MAX),
        step              VARCHAR(4),
        connection_id     VARCHAR(32),
        source_job_id     VARCHAR(36),
        CONSTRAINT chk_status CHECK (
            status IN ('draft', 'queued', 'running', 'cancelling', 'cancelled', 'done', 'error')
        ),
        CONSTRAINT chk_jobs_params_json CHECK (params IS NULL OR ISJSON(params) = 1),
        CONSTRAINT chk_jobs_log_json CHECK (log IS NULL OR ISJSON(log) = 1),
        -- NO ACTION, not SET NULL: SQL Server refuses a self-referencing FK
        -- with a cascading action once a second FK (fk_jobs_connection_id,
        -- below) exists on the same table - it can't prove there's no cycle
        -- or multiple cascade path, even though this one can't actually form
        -- one. Jobs are never hard-deleted in this app (they're an audit
        -- trail), so the lack of auto-null-on-delete here is not reachable
        -- in practice.
        CONSTRAINT fk_jobs_source_job_id FOREIGN KEY (source_job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE NO ACTION
    );
END;

-- ============================================================================
-- 2. saved_connections
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'saved_connections')
BEGIN
    CREATE TABLE dbo.saved_connections (
        id                           VARCHAR(32)  NOT NULL PRIMARY KEY,
        name                         VARCHAR(255) NOT NULL,
        db_type                      VARCHAR(50)  NOT NULL,
        description                  NVARCHAR(MAX),
        connection_details_encrypted NVARCHAR(MAX) NOT NULL,
        -- Nullable: rows created by an earlier build predate ownership. Those
        -- legacy rows are usable by everyone and manageable only by an admin
        -- (SavedConnectionService._require_owner).
        created_by                   VARCHAR(255),
        created_at                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

-- SQL Server's default collation (SQL_Latin1_General_CP1_CI_AS) is already
-- case-insensitive, so the Postgres expression index on lower(name) isn't
-- needed - a plain unique index on `name` already behaves the same way.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'uq_saved_connections_name')
BEGIN
    CREATE UNIQUE INDEX uq_saved_connections_name ON dbo.saved_connections (name);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_saved_connections_created_at')
BEGIN
    CREATE INDEX idx_saved_connections_created_at ON dbo.saved_connections (created_at DESC);
END;

-- jobs' FK to saved_connections, added after both tables exist.
IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'fk_jobs_connection_id')
BEGIN
    ALTER TABLE dbo.jobs
        ADD CONSTRAINT fk_jobs_connection_id
        FOREIGN KEY (connection_id) REFERENCES dbo.saved_connections (id)
        ON DELETE SET NULL;
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_started_at')
BEGIN
    CREATE INDEX idx_jobs_started_at ON dbo.jobs (started_at DESC);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_status')
BEGIN
    CREATE INDEX idx_jobs_status ON dbo.jobs (status);
END;

-- Serves the V2 jobs list (filtered by step+status per owner, polled every 1.4s).
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_owner_step_status')
BEGIN
    CREATE INDEX idx_jobs_owner_step_status
        ON dbo.jobs (created_by, step, status, started_at DESC);
END;

-- Serves job_reconciler.py's 60s sweep for non-terminal jobs. A filtered
-- index keeps that a small lookup as jobs history grows. SQL Server filtered
-- index predicates only allow AND to chain conditions (not OR), but IN is
-- allowed directly, so this ports unchanged from the Postgres original.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_active_status')
BEGIN
    CREATE INDEX idx_jobs_active_status
        ON dbo.jobs (started_at)
        WHERE status IN ('queued', 'running', 'cancelling');
END;

-- ============================================================================
-- 3. profile_map_results
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'profile_map_results')
BEGIN
    CREATE TABLE dbo.profile_map_results (
        job_id        VARCHAR(36) NOT NULL PRIMARY KEY,
        rows          NVARCHAR(MAX) NOT NULL,
        version       INT NOT NULL DEFAULT 1,
        row_count     INT NOT NULL DEFAULT 0,
        created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by    VARCHAR(255),
        failed_tables NVARCHAR(MAX) NOT NULL DEFAULT '[]',
        CONSTRAINT chk_pmr_rows_json CHECK (ISJSON(rows) = 1),
        CONSTRAINT chk_pmr_failed_tables_json CHECK (ISJSON(failed_tables) = 1),
        CONSTRAINT fk_pmr_job_id FOREIGN KEY (job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE CASCADE
    );
END;

-- ============================================================================
-- 4. profile_map_edits
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'profile_map_edits')
BEGIN
    CREATE TABLE dbo.profile_map_edits (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        job_id        VARCHAR(36)  NOT NULL,
        table_name    VARCHAR(255) NOT NULL,
        column_name   VARCHAR(255) NOT NULL,
        field         VARCHAR(64)  NOT NULL,
        old_value     NVARCHAR(MAX),
        new_value     NVARCHAR(MAX),
        version_after INT NOT NULL,
        edited_by     VARCHAR(255) NOT NULL,
        edited_at     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        -- Python-generated (str(uuid.uuid4())), never DB-generated.
        row_id        VARCHAR(36) NOT NULL,
        CONSTRAINT fk_pme_job_id FOREIGN KEY (job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_profile_map_edits_job')
BEGIN
    CREATE INDEX idx_profile_map_edits_job ON dbo.profile_map_edits (job_id, edited_at DESC);
END;

-- ============================================================================
-- 5. validation_results
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'validation_results')
BEGIN
    CREATE TABLE dbo.validation_results (
        job_id        VARCHAR(36) NOT NULL PRIMARY KEY,
        -- A 0..1 fraction at 4-decimal precision, not a percentage.
        overall_score NUMERIC(6, 4),
        summary       NVARCHAR(MAX) NOT NULL,
        created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT chk_vr_summary_json CHECK (ISJSON(summary) = 1),
        CONSTRAINT fk_vr_job_id FOREIGN KEY (job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_validation_results_created_at')
BEGIN
    CREATE INDEX idx_validation_results_created_at ON dbo.validation_results (created_at DESC);
END;

-- ============================================================================
-- 6. sessions
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sessions')
BEGIN
    CREATE TABLE dbo.sessions (
        session_id VARCHAR(64)  NOT NULL PRIMARY KEY,
        username   VARCHAR(255) NOT NULL,
        expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 DEFAULT SYSUTCDATETIME()
    );
END;

-- ============================================================================
-- 7. notifications (the bell in the top bar)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'notifications')
BEGIN
    CREATE TABLE dbo.notifications (
        id         BIGINT IDENTITY(1,1) PRIMARY KEY,
        username   VARCHAR(255)  NOT NULL,
        -- A short slug (job_done / job_error / ...). Deliberately not a
        -- CHECK-ed enum: the UI falls back to a neutral icon for an unknown
        -- type, so a new type is a code change, not a migration.
        type       VARCHAR(32)   NOT NULL,
        title      VARCHAR(200)  NOT NULL,
        content    NVARCHAR(MAX) NOT NULL DEFAULT '',
        status     VARCHAR(10)   NOT NULL DEFAULT 'unread',
        -- An in-app path such as /validator/<job id>, never a full URL -
        -- enforced here and in the API so no writer can send a user off-site.
        link       VARCHAR(500),
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT chk_notifications_status CHECK (status IN ('unread', 'read')),
        CONSTRAINT chk_notifications_link CHECK (
            link IS NULL
            OR (LEFT(link, 1) = '/' AND LEFT(link, 2) <> '//' AND CHARINDEX(CHAR(92), link) = 0)
        )
    );
END;

-- Serves the list (newest first, keyset-paged on id) and the live stream
-- (id > last seen), both per user.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_notifications_user_id')
BEGIN
    CREATE INDEX idx_notifications_user_id ON dbo.notifications (username, id DESC);
END;

-- Serves the unread badge count and "mark all as read". Filtered, so it stays
-- small no matter how much read history accumulates.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_notifications_user_unread')
BEGIN
    CREATE INDEX idx_notifications_user_unread
        ON dbo.notifications (username)
        WHERE status = 'unread';
END;

GO

-- ============================================================================
-- 8. Job-finished trigger
-- ============================================================================
-- Covers profiling (step 1) and validation (step 3) jobs. Fires once per
-- UPDATE statement over inserted/deleted (T-SQL triggers are set-based, not
-- per-row like Postgres's FOR EACH ROW), only when `status` actually changed
-- into a terminal value. TRY/CATCH stands in for Postgres's subtransaction:
-- a notification is a courtesy and must never be able to roll back the
-- status change it is reporting.
--
-- CREATE TRIGGER must be the only statement in its batch, hence the GO above.

CREATE TRIGGER trg_jobs_notify_finished ON dbo.jobs
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT UPDATE(status)
        RETURN;

    BEGIN TRY
        INSERT INTO dbo.notifications (username, type, title, content, link)
        SELECT
            i.created_by,
            CASE i.status
                WHEN 'done'  THEN 'job_done'
                WHEN 'error' THEN 'job_error'
                ELSE 'job_cancelled'
            END,
            LEFT(
                CASE WHEN i.step = '3' THEN 'Validator' ELSE 'Profile Mapper' END
                + ' job '
                + CASE i.status
                      WHEN 'done'  THEN 'completed'
                      WHEN 'error' THEN 'failed'
                      ELSE 'cancelled'
                  END,
                200
            ),
            LEFT(
                '"' + COALESCE(NULLIF(LTRIM(RTRIM(i.name)), ''), i.job_id) + '" '
                + CASE i.status
                      WHEN 'done'  THEN 'finished successfully.'
                      WHEN 'error' THEN 'did not finish. Open the job for details.'
                      ELSE 'was cancelled.'
                  END,
                1000
            ),
            CASE WHEN i.step = '3' THEN '/validator/' ELSE '/profile-mapper/' END + i.job_id
        FROM inserted i
        INNER JOIN deleted d ON d.job_id = i.job_id
        WHERE i.status <> d.status
          AND i.status IN ('done', 'error', 'cancelled')
          AND i.created_by IS NOT NULL
          AND LTRIM(RTRIM(i.created_by)) <> '';
    END TRY
    BEGIN CATCH
        -- Swallow and move on - see comment above. Surfaced to the server
        -- log rather than raised, so it can never take the status change
        -- (or the caller's transaction) down with it.
        PRINT 'trg_jobs_notify_finished: ' + ERROR_MESSAGE();
    END CATCH
END;

GO

-- ============================================================================
-- 9. Seed: one local admin login
-- ============================================================================
-- password_hash is sha256$<hex of the plaintext>, the exact format
-- utils/password_hash.hash_password produces. The plaintext was shown once in
-- chat when this migration was written; it is never stored anywhere in the repo.

IF NOT EXISTS (SELECT * FROM dbo.users WHERE user_name = 'admin@email.com')
BEGIN
    INSERT INTO dbo.users (user_name, password_hash, is_active, is_admin, user_email_id)
    VALUES (
        'admin@email.com',
        'sha256$df813112f7c5a445078a4e5edee300e390733e268487b937cd0ba9525f23a1ef',
        1,
        1,
        'admin@email.com'
    );
END;
