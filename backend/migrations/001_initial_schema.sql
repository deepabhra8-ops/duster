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
        glue_job_run_id   VARCHAR(100),
        started_at        DATETIME2 DEFAULT SYSUTCDATETIME(),
        completed_at      DATETIME2,
        created_by        VARCHAR(255),
        error_message     NVARCHAR(MAX),
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
        CONSTRAINT fk_jobs_source_job_id FOREIGN KEY (source_job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'saved_connections')
BEGIN
    CREATE TABLE dbo.saved_connections (
        id                           VARCHAR(32)  NOT NULL PRIMARY KEY,
        name                         VARCHAR(255) NOT NULL,
        db_type                      VARCHAR(50)  NOT NULL,
        description                  NVARCHAR(MAX),
        connection_details_encrypted NVARCHAR(MAX) NOT NULL,
        created_by                   VARCHAR(255),
        created_at                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'uq_saved_connections_name')
BEGIN
    CREATE UNIQUE INDEX uq_saved_connections_name ON dbo.saved_connections (name);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_saved_connections_created_at')
BEGIN
    CREATE INDEX idx_saved_connections_created_at ON dbo.saved_connections (created_at DESC);
END;

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

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_owner_step_status')
BEGIN
    CREATE INDEX idx_jobs_owner_step_status
        ON dbo.jobs (created_by, step, status, started_at DESC);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_jobs_active_status')
BEGIN
    CREATE INDEX idx_jobs_active_status
        ON dbo.jobs (started_at)
        WHERE status IN ('queued', 'running', 'cancelling');
END;

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
        row_id        VARCHAR(36) NOT NULL,
        CONSTRAINT fk_pme_job_id FOREIGN KEY (job_id)
            REFERENCES dbo.jobs (job_id) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_profile_map_edits_job')
BEGIN
    CREATE INDEX idx_profile_map_edits_job ON dbo.profile_map_edits (job_id, edited_at DESC);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'validation_results')
BEGIN
    CREATE TABLE dbo.validation_results (
        job_id        VARCHAR(36) NOT NULL PRIMARY KEY,
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

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sessions')
BEGIN
    CREATE TABLE dbo.sessions (
        session_id VARCHAR(64)  NOT NULL PRIMARY KEY,
        username   VARCHAR(255) NOT NULL,
        expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'notifications')
BEGIN
    CREATE TABLE dbo.notifications (
        id         BIGINT IDENTITY(1,1) PRIMARY KEY,
        username   VARCHAR(255)  NOT NULL,
        type       VARCHAR(32)   NOT NULL,
        title      VARCHAR(200)  NOT NULL,
        content    NVARCHAR(MAX) NOT NULL DEFAULT '',
        status     VARCHAR(10)   NOT NULL DEFAULT 'unread',
        link       VARCHAR(500),
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT chk_notifications_status CHECK (status IN ('unread', 'read')),
        CONSTRAINT chk_notifications_link CHECK (
            link IS NULL
            OR (LEFT(link, 1) = '/' AND LEFT(link, 2) <> '//' AND CHARINDEX(CHAR(92), link) = 0)
        )
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_notifications_user_id')
BEGIN
    CREATE INDEX idx_notifications_user_id ON dbo.notifications (username, id DESC);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_notifications_user_unread')
BEGIN
    CREATE INDEX idx_notifications_user_unread
        ON dbo.notifications (username)
        WHERE status = 'unread';
END;

GO

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
        PRINT 'trg_jobs_notify_finished: ' + ERROR_MESSAGE();
    END CATCH
END;

GO

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
