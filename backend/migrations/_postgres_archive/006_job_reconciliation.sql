CREATE INDEX IF NOT EXISTS idx_jobs_active_status
    ON jobs (started_at)
    WHERE status IN ('queued', 'running', 'cancelling');

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
