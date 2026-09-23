-- Migration 007: stop caching schema names on the connection.
--
-- 003 removed the whole-catalog cache but deliberately kept the schema *name
-- list*, on the reasoning that it was small and made the first dropdown instant.
-- In practice that trade did not pay:
--
--   * It made saving a connection slow. Creating one ran a catalog query before
--     it returned, so the UI sat on "fetching schemas" for a step the user had
--     not asked for and did not need - they were saving a connection, not
--     building a job.
--   * It could go stale. A schema added to the source after the connection was
--     saved never appeared until someone thought to hit refresh, and nothing in
--     the UI suggested that was necessary.
--   * It was inconsistent. Tables and columns were already read live, per
--     selection; schemas were the one level still served from a cache.
--
-- Schemas are now read live from the source the same way tables and columns are -
-- one catalog query, made when a connection is actually picked for a profiling or
-- validation job. Saving a connection now does no catalog work at all.
--
-- Nothing of value is lost here: both columns held a re-derivable cache, and the
-- credentials needed to re-derive it stay in connection_details_encrypted.

BEGIN;

ALTER TABLE saved_connections DROP COLUMN IF EXISTS schemas;
ALTER TABLE saved_connections DROP COLUMN IF EXISTS schemas_fetched_at;

COMMIT;
