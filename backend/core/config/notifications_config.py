"""In-app notification stream and retention settings."""

import os


# How often each open notification stream (services/notifications/notification_stream.py)
# asks the database for rows it has not yet sent. A poll rather than a push because
# notifications are written by a database trigger (see trg_jobs_notify_finished
# in migrations/001), not by this request - so this query is the only way a
# stream learns of them. Lower is snappier; the cost is one small indexed query
# per open tab.
NOTIFICATION_STREAM_POLL_SECONDS = float(os.getenv("NOTIFICATION_STREAM_POLL_SECONDS", "3"))

# How many days a READ notification is kept, counted from when it was created (not from when it
# was read). Older read ones are hard-deleted by services/notifications/notification_retention.py.
# Unread notifications are never deleted, however old. Zero or negative DISABLES the sweep - it
# never means "delete everything".
NOTIFICATION_RETENTION_DAYS = int(os.getenv("NOTIFICATION_RETENTION_DAYS", "7"))

# Whether this process runs that sweep. On by default; every worker runs one and they cooperate
# through row locks. Turn it off for a container that only runs a one-off task (e.g. migrations),
# which has no business deleting data.
RUN_NOTIFICATION_PURGE = os.getenv("RUN_NOTIFICATION_PURGE", "true").strip().lower() == "true"
