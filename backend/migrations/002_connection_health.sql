IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'last_tested_at'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD last_tested_at DATETIME2 NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'last_test_status'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD last_test_status VARCHAR(20) NOT NULL DEFAULT 'unknown';
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints
    WHERE name = 'chk_saved_connections_last_test_status'
)
BEGIN
    ALTER TABLE dbo.saved_connections
        ADD CONSTRAINT chk_saved_connections_last_test_status
        CHECK (last_test_status IN ('healthy', 'warning', 'error', 'unknown'));
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'last_test_error'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD last_test_error NVARCHAR(MAX) NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'schema_count'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD schema_count INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'table_count'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD table_count INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'last_rotated_at'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD last_rotated_at DATETIME2 NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.saved_connections') AND name = 'rotation_reminded_at'
)
BEGIN
    ALTER TABLE dbo.saved_connections ADD rotation_reminded_at DATETIME2 NULL;
END;
GO

-- Backfill existing rows so rotation-age checks have a starting point.
UPDATE dbo.saved_connections
SET last_rotated_at = created_at
WHERE last_rotated_at IS NULL;
GO
