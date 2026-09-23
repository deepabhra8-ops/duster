BEGIN;

ALTER TABLE saved_connections DROP COLUMN IF EXISTS port;

ALTER TABLE saved_connections DROP CONSTRAINT IF EXISTS chk_conn_scan_status;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan_status;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan_error;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scanned_at;

ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS schemas JSONB;
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS schemas_fetched_at TIMESTAMP;

ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan;
ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan_status;
ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan_error;

COMMIT;
