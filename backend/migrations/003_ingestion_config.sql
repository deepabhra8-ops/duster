IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ingestion_configs')
BEGIN
    CREATE TABLE dbo.ingestion_configs (
        connection_id        VARCHAR(32)  NOT NULL PRIMARY KEY,
        system_type          VARCHAR(20)  NOT NULL,
        latency_requirement  VARCHAR(20)  NOT NULL,
        scheduling_ownership VARCHAR(20)  NOT NULL,
        ingestion_mode       VARCHAR(10)  NOT NULL,
        created_at           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT chk_ingestion_configs_system_type CHECK (
            system_type IN ('warehouse', 'database', 'lake', 'event_stream', 'saas')
        ),
        CONSTRAINT chk_ingestion_configs_latency CHECK (
            latency_requirement IN ('real_time', 'hourly', 'daily')
        ),
        CONSTRAINT chk_ingestion_configs_ownership CHECK (
            scheduling_ownership IN ('saas', 'customer')
        ),
        CONSTRAINT chk_ingestion_configs_mode CHECK (
            ingestion_mode IN ('pull', 'push', 'poll')
        ),
        CONSTRAINT fk_ingestion_configs_connection_id FOREIGN KEY (connection_id)
            REFERENCES dbo.saved_connections (id) ON DELETE CASCADE
    );
END;
