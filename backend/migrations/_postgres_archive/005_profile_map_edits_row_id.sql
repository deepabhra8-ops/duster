-- Add row_id UUID column to profile_map_edits, allow null initially.
-- IF NOT EXISTS so this file stays individually idempotent, per the contract
-- run_migrations.py relies on to adopt a database that was migrated by hand.
ALTER TABLE profile_map_edits ADD COLUMN IF NOT EXISTS row_id UUID;

-- Backfill with gen_random_uuid()
UPDATE profile_map_edits SET row_id = gen_random_uuid() WHERE row_id IS NULL;

-- Set NOT NULL constraint
ALTER TABLE profile_map_edits ALTER COLUMN row_id SET NOT NULL;
