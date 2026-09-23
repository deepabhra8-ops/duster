-- Support for the job reconciler (backend/services/job_reconciler.py).
--
-- Individually idempotent, per the contract run_migrations.py relies on to
-- adopt a database that was migrated by hand.

-- The reconciler sweeps for jobs still in a non-terminal state every 60s. A
-- partial index keeps that a small lookup as the jobs table grows: only the
-- handful of live rows are indexed, not the whole history of finished runs.
CREATE INDEX IF NOT EXISTS idx_jobs_active_status
    ON jobs (started_at)
    WHERE status IN ('queued', 'running', 'cancelling');

-- Jobs stranded before the reconciler existed. Their outcome is genuinely
-- unknown: the only thing that ever wrote running -> done was a thread inside a
-- Uvicorn worker, and for these rows that worker is long gone. Anything still
-- "active" after a day cannot be in flight - the Glue run's own timeout is far
-- shorter than that - so they are closed out with an explanation rather than
-- left spinning in the UI forever.
UPDATE jobs
SET status = 'error',
    completed_at = COALESCE(completed_at, now()),
    error_message = COALESCE(
        error_message,
        'Job was left in an unfinished state by a previous build, which tracked '
        'Glue runs only in the memory of the worker that started them. Its real '
        'outcome was not recorded. Please run it again.'
    )
WHERE status IN ('queued', 'running', 'cancelling')
  AND started_at < now() - INTERVAL '24 hours';
