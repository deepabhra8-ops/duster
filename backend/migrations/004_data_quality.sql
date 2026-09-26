IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'dq_rules')
BEGIN
    CREATE TABLE dbo.dq_rules (
        id                INT IDENTITY(1,1) PRIMARY KEY,
        rule_name         VARCHAR(128)   NOT NULL,
        description       NVARCHAR(1000) NULL,
        template          VARCHAR(64)    NOT NULL,
        dimension         VARCHAR(32)    NULL,
        params            NVARCHAR(MAX)  NOT NULL DEFAULT '{}',
        applies_to        NVARCHAR(400)  NULL,
        null_policy       VARCHAR(10)    NOT NULL DEFAULT 'ignore',
        row_filter        NVARCHAR(MAX)  NULL,
        threshold_metric  VARCHAR(16)    NOT NULL,
        threshold_op      VARCHAR(2)     NOT NULL,
        threshold_value   FLOAT          NOT NULL,
        severity          VARCHAR(8)     NOT NULL DEFAULT 'error',
        weight            FLOAT          NOT NULL DEFAULT 1.0,
        scope_level       VARCHAR(10)    NULL,
        scope_catalog     NVARCHAR(255)  NOT NULL DEFAULT '*',
        scope_schema      NVARCHAR(255)  NOT NULL DEFAULT '*',
        scope_table       NVARCHAR(255)  NOT NULL DEFAULT '*',
        scope_column      NVARCHAR(255)  NOT NULL DEFAULT '*',
        scope_exclude     NVARCHAR(MAX)  NOT NULL DEFAULT '[]',
        scope_table_types NVARCHAR(200)  NOT NULL DEFAULT '["MANAGED","EXTERNAL"]',
        enabled           BIT            NOT NULL DEFAULT 1,
        version           INT            NOT NULL DEFAULT 1,
        last_run_id       VARCHAR(36)    NULL,
        last_run_at       DATETIME2      NULL,
        last_run_counts   NVARCHAR(MAX)  NULL,
        created_by        VARCHAR(255)   NULL,
        updated_by        VARCHAR(255)   NULL,
        created_at        DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at        DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT chk_dq_rules_null_policy CHECK (null_policy IN ('ignore', 'fail')),
        CONSTRAINT chk_dq_rules_threshold_metric CHECK (threshold_metric IN ('pass_rate', 'value')),
        CONSTRAINT chk_dq_rules_threshold_op CHECK (threshold_op IN ('>=', '<=', '>', '<', '==')),
        CONSTRAINT chk_dq_rules_severity CHECK (severity IN ('info', 'warn', 'error')),
        CONSTRAINT chk_dq_rules_scope_level CHECK (
            scope_level IS NULL OR scope_level IN ('column', 'table', 'schema', 'catalog', 'all')
        ),
        CONSTRAINT chk_dq_rules_params_json CHECK (ISJSON(params) = 1),
        CONSTRAINT chk_dq_rules_applies_to_json CHECK (applies_to IS NULL OR ISJSON(applies_to) = 1),
        CONSTRAINT chk_dq_rules_exclude_json CHECK (ISJSON(scope_exclude) = 1),
        CONSTRAINT chk_dq_rules_table_types_json CHECK (ISJSON(scope_table_types) = 1),
        CONSTRAINT chk_dq_rules_last_run_counts_json CHECK (last_run_counts IS NULL OR ISJSON(last_run_counts) = 1)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'uq_dq_rules_name')
BEGIN
    CREATE UNIQUE INDEX uq_dq_rules_name ON dbo.dq_rules (rule_name);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'dq_runs')
BEGIN
    CREATE TABLE dbo.dq_runs (
        run_id              VARCHAR(36)   NOT NULL PRIMARY KEY,
        status              VARCHAR(12)   NOT NULL DEFAULT 'queued',
        requested_by        VARCHAR(255)  NULL,
        rule_ids            NVARCHAR(MAX) NULL,
        scope_override      NVARCHAR(MAX) NULL,
        where_clause        NVARCHAR(MAX) NULL,
        sample_fraction     FLOAT         NULL,
        max_parallel_tables INT           NOT NULL DEFAULT 4,
        rule_count          INT           NOT NULL DEFAULT 0,
        table_count         INT           NOT NULL DEFAULT 0,
        result_count        INT           NOT NULL DEFAULT 0,
        progress_current    INT           NOT NULL DEFAULT 0,
        progress_total      INT           NOT NULL DEFAULT 0,
        error_message       NVARCHAR(MAX) NULL,
        engine_version      VARCHAR(16)   NULL,
        created_at          DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        started_at          DATETIME2     NULL,
        completed_at        DATETIME2     NULL,
        duration_ms         BIGINT        NULL,
        CONSTRAINT chk_dq_runs_status CHECK (
            status IN ('queued', 'running', 'cancelling', 'cancelled', 'done', 'error')
        ),
        CONSTRAINT chk_dq_runs_rule_ids_json CHECK (rule_ids IS NULL OR ISJSON(rule_ids) = 1),
        CONSTRAINT chk_dq_runs_scope_json CHECK (scope_override IS NULL OR ISJSON(scope_override) = 1)
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_dq_runs_created_at')
BEGIN
    CREATE INDEX idx_dq_runs_created_at ON dbo.dq_runs (created_at DESC);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_dq_runs_status_completed')
BEGIN
    CREATE INDEX idx_dq_runs_status_completed ON dbo.dq_runs (status, completed_at DESC);
END;

-- Append-only, one row per rule x target (§3.3 of the design). Scores are never
-- stored here; they're rolled up from these raw counts when a run is read.
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'dq_results')
BEGIN
    CREATE TABLE dbo.dq_results (
        id               BIGINT IDENTITY(1,1) PRIMARY KEY,
        run_id           VARCHAR(36)    NOT NULL,
        rule_id          VARCHAR(16)    NOT NULL,
        rule_name        VARCHAR(128)   NOT NULL,
        rule_version     INT            NULL,
        template         VARCHAR(64)    NOT NULL,
        dimension        VARCHAR(32)    NULL,
        rule_level       VARCHAR(16)    NOT NULL,
        severity         VARCHAR(8)     NOT NULL,
        weight           FLOAT          NULL,
        catalog_name     NVARCHAR(255)  NULL,
        schema_name      NVARCHAR(255)  NULL,
        table_name       NVARCHAR(255)  NULL,
        column_name      NVARCHAR(255)  NULL,
        total_count      BIGINT         NULL,
        pass_count       BIGINT         NULL,
        fail_count       BIGINT         NULL,
        metric_value     FLOAT          NULL,
        threshold_metric VARCHAR(16)    NOT NULL,
        threshold_op     VARCHAR(2)     NOT NULL,
        threshold_value  FLOAT          NOT NULL,
        status           VARCHAR(8)     NOT NULL,
        message          NVARCHAR(2000) NULL,
        where_clause     NVARCHAR(MAX)  NULL,
        sampled          BIT            NOT NULL DEFAULT 0,
        sample_fraction  FLOAT          NULL,
        duration_ms      BIGINT         NULL,
        CONSTRAINT chk_dq_results_status CHECK (
            status IN ('PASS', 'WARN', 'FAIL', 'ERROR', 'SKIPPED', 'NO_DATA')
        ),
        CONSTRAINT fk_dq_results_run_id FOREIGN KEY (run_id)
            REFERENCES dbo.dq_runs (run_id) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_dq_results_run_status')
BEGIN
    CREATE INDEX idx_dq_results_run_status ON dbo.dq_results (run_id, status);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_dq_results_rule_run')
BEGIN
    CREATE INDEX idx_dq_results_rule_run ON dbo.dq_results (rule_id, run_id);
END;
