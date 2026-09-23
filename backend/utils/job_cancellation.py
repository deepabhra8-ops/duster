"""Shared exception used to unwind pipeline execution when a job's cancellation has been requested."""


class JobCancelledError(Exception):
    """Raised by an engine's per-table loop to abort a job once its cancel_event is set."""
