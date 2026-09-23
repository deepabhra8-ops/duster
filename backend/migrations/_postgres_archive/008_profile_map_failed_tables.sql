-- Migration 008: record the tables a profiling run had to skip.
--
-- A multi-table run (several flat files, or several database tables) now keeps
-- the tables that profiled successfully when another one fails, rather than
-- failing the whole job. The skipped tables and why are stored here as
-- [{"table": ..., "error": ...}] so the results page can tell the user which
-- one is missing. Written by glue/job_state_writer.py on every run.
--
-- Individually idempotent, per the contract run_migrations.py relies on.

BEGIN;

ALTER TABLE profile_map_results
    ADD COLUMN IF NOT EXISTS failed_tables JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
