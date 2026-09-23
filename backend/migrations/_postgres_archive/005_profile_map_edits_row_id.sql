ALTER TABLE profile_map_edits ADD COLUMN IF NOT EXISTS row_id UUID;

UPDATE profile_map_edits SET row_id = gen_random_uuid() WHERE row_id IS NULL;

ALTER TABLE profile_map_edits ALTER COLUMN row_id SET NOT NULL;
