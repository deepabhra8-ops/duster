-- Migration 003: stop caching whole database catalogs.
--
-- 002 stored an entire schema->table->column tree per connection (and again per
-- draft job) in JSONB, populated by walking the whole catalog when a connection
-- was saved. On a large database that walk is slow enough to stall the save, the
-- payload is large, and it goes stale the moment anyone changes the source.
--
-- Replaced by: store only the schema *name list* (small, enough to make the first
-- dropdown instant) and fetch tables for a chosen schema, then columns for a
-- chosen table, live from the browser.
--
-- Data dropped here is a cache - it is re-derivable on demand - and `port` was
-- always redundant with the port already inside connection_details_encrypted.

BEGIN;

-- ── saved_connections ────────────────────────────────────────────────

-- Redundant: the port lives in the encrypted connection details. It was also
-- NULL for every connector that has no port concept (Snowflake, Databricks,
-- BigQuery, Salesforce), so it could not be relied on anyway.
ALTER TABLE saved_connections DROP COLUMN IF EXISTS port;

-- The whole-catalog cache and the async status machinery that fed it.
ALTER TABLE saved_connections DROP CONSTRAINT IF EXISTS chk_conn_scan_status;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan_status;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scan_error;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS metadata_scanned_at;

-- Just the schema names, e.g. ["public", "analytics"]. Small enough to store and
-- return with the connection, which is what makes the schema dropdown instant.
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS schemas JSONB;
ALTER TABLE saved_connections ADD COLUMN IF NOT EXISTS schemas_fetched_at TIMESTAMP;

-- ── jobs ─────────────────────────────────────────────────────────────

-- A draft job no longer carries its own copy of the catalog; the UI reads
-- tables/columns live from the connection while the user builds the job.
ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan;
ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan_status;
ALTER TABLE jobs DROP COLUMN IF EXISTS metadata_scan_error;

COMMIT;
