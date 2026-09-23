BEGIN;

CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL     PRIMARY KEY,
    username    VARCHAR(255)  NOT NULL,
    type        VARCHAR(32)   NOT NULL,
    title       VARCHAR(200)  NOT NULL,
    content     TEXT          NOT NULL DEFAULT '',
    status      VARCHAR(10)   NOT NULL DEFAULT 'unread',
    link        VARCHAR(500),
    created_at  TIMESTAMP     NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_notifications_status CHECK (status IN ('unread', 'read')),
    CONSTRAINT chk_notifications_link CHECK (
        link IS NULL
        OR (left(link, 1) = '/' AND left(link, 2) <> '//' AND strpos(link, chr(92)) = 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id
    ON notifications (username, id DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications (username)
    WHERE status = 'unread';

CREATE OR REPLACE FUNCTION notify_job_finished() RETURNS trigger AS $$
BEGIN
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

DROP TRIGGER IF EXISTS trg_jobs_notify_finished ON jobs;

CREATE TRIGGER trg_jobs_notify_finished
    AFTER UPDATE OF status ON jobs
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status
          AND NEW.status IN ('done', 'error', 'cancelled'))
    EXECUTE PROCEDURE notify_job_finished();

COMMIT;
