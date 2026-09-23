BEGIN;

ALTER TABLE profile_map_results
    ADD COLUMN IF NOT EXISTS failed_tables JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
