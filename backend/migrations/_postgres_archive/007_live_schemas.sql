BEGIN;

ALTER TABLE saved_connections DROP COLUMN IF EXISTS schemas;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS schemas_fetched_at;

COMMIT;
