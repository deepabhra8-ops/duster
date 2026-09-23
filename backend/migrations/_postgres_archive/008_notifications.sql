-- Migration 008: in-app notifications (the bell in the top bar).
--
-- Every statement is idempotent so this file can be re-applied safely.
--
-- 1. The notifications table, keyed by `username` rather than a user id: the app
--    identifies people by username everywhere (jobs.created_by, sessions.username)
--    and the users table is managed by another system, so there is no id of ours
--    to reference.
--
-- 2. A trigger that records a notification whenever a job reaches a terminal
--    state. It is a trigger rather than application code because three different
--    writers move jobs to done/error/cancelled - the Glue run itself
--    (glue/job_state_writer.py, a separately deployed wheel that writes straight
--    to Postgres), the web tier's reconciler, and the job service. Hooking any
--    one of them leaves the others silent, and the Glue run is the one that
--    finishes almost every job. A trigger sees all of them, fires exactly once
--    per transition, and commits atomically with the status change.

BEGIN;

-- ============================================================================
-- 1. Notifications
-- ============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL     PRIMARY KEY,
    username    VARCHAR(255)  NOT NULL,
    -- A short slug such as job_done / job_error. Deliberately not a CHECK-ed
    -- enum: the UI maps known types to an icon and falls back to a neutral one,
    -- so a new type is a code change and not a migration.
    type        VARCHAR(32)   NOT NULL,
    title       VARCHAR(200)  NOT NULL,
    content     TEXT          NOT NULL DEFAULT '',
    status      VARCHAR(10)   NOT NULL DEFAULT 'unread',
    -- An in-app path such as /validator/<job id>, never a full URL: clicking a
    -- notification navigates, so an absolute link would let anything able to
    -- create a row send a user to an external site. Enforced here as well as in
    -- the API so no other writer can bypass it.
    link        VARCHAR(500),
    -- Naive UTC, matching the other tables; the API tags it as UTC on the way out.
    created_at  TIMESTAMP     NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_notifications_status CHECK (status IN ('unread', 'read')),
    CONSTRAINT chk_notifications_link CHECK (
        link IS NULL
        OR (left(link, 1) = '/' AND left(link, 2) <> '//' AND strpos(link, chr(92)) = 0)
    )
);

-- Serves the list (newest first, keyset-paged on id) and the live stream
-- (`id > last seen`), both per user.
CREATE INDEX IF NOT EXISTS idx_notifications_user_id
    ON notifications (username, id DESC);

-- Serves the unread badge count and "mark all as read". Partial, so it stays
-- small no matter how much read history accumulates.
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications (username)
    WHERE status = 'unread';


-- ============================================================================
-- 2. Job-finished trigger
-- ============================================================================
-- Covers profiling (step 1) and validation (step 3) jobs. The message is built
-- here from the job row; the raw error text is intentionally NOT copied in - it
-- can be an entire traceback, and the job page already shows it to the owner.
--
-- The insert sits in its own BEGIN/EXCEPTION block, which is a subtransaction.
-- A notification is a courtesy; it must never be able to roll back the status
-- change it is reporting, or a bug here would strand a finished job at
-- "running" - the very failure job_reconciler.py exists to clean up after. If the
-- insert fails, the job still completes and the reason goes to the server log.

CREATE OR REPLACE FUNCTION notify_job_finished() RETURNS trigger AS $$
BEGIN
    -- Jobs from before ownership was recorded have no one to tell.
    IF NEW.created_by IS NULL OR btrim(NEW.created_by) = '' THEN
        RETURN NEW;
    END IF;

    BEGIN
        INSERT INTO notifications (username, type, title, content, link)
        VALUES (
            NEW.created_by,
            CASE NEW.status
                WHEN 'done'  THEN 'job_done'
                WHEN 'error' THEN 'job_error'
                ELSE 'job_cancelled'
            END,
            left(
                CASE WHEN NEW.step = '3' THEN 'Validator' ELSE 'Profile Mapper' END
                || ' job '
                || CASE NEW.status
                       WHEN 'done'  THEN 'completed'
                       WHEN 'error' THEN 'failed'
                       ELSE 'cancelled'
                   END,
                200
            ),
            left(
                '"' || COALESCE(NULLIF(btrim(NEW.name), ''), NEW.job_id) || '" '
                || CASE NEW.status
                       WHEN 'done'  THEN 'finished successfully.'
                       WHEN 'error' THEN 'did not finish. Open the job for details.'
                       ELSE 'was cancelled.'
                   END,
                1000
            ),
            CASE WHEN NEW.step = '3' THEN '/validator/' ELSE '/profile-mapper/' END
                || NEW.job_id
        );
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'notify_job_finished: no notification recorded for job %, %', NEW.job_id, SQLERRM;
    END;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Fires on a real change into a terminal state only. `OF status` alone would
-- also fire on the frequent progress/log updates that merely list status in the
-- SET clause; the WHEN condition is what makes this once-per-transition.
DROP TRIGGER IF EXISTS trg_jobs_notify_finished ON jobs;

CREATE TRIGGER trg_jobs_notify_finished
    AFTER UPDATE OF status ON jobs
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status
          AND NEW.status IN ('done', 'error', 'cancelled'))
    EXECUTE PROCEDURE notify_job_finished();

COMMIT;
