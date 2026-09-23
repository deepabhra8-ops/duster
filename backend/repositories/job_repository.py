"""SQLAlchemy-backed repository for job state."""

from typing import Any

from sqlalchemy import case, func, or_, text

from core.db import get_db_session
from repositories.models import Job, SavedConnection
from utils.logger import get_logger

logger = get_logger(__name__)


class JobRepository:
    """SQLAlchemy-backed repository for job state."""

    def create(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Create a new job."""
        try:
            with get_db_session() as session:
                progress = job_data.get("progress", {})
                job = Job(
                    job_id=job_id,
                    status=job_data.get("status", "queued"),
                    params=job_data.get("params"),
                    log=job_data.get("log", []),
                    report_path=job_data.get("report_path"),
                    profile_path=job_data.get("profile_path"),
                    staging_path=job_data.get("staging_path"),
                    progress_current=progress.get("current", 0),
                    progress_total=progress.get("total", 0),
                    created_by=job_data.get("created_by"),
                    name=job_data.get("name"),
                    description=job_data.get("description"),
                    step=job_data.get("step"),
                    connection_id=job_data.get("connection_id"),
                    source_job_id=job_data.get("source_job_id"),
                )
                session.add(job)
                session.commit()
                logger.info("Created job %s in RDS", job_id)
        except Exception as exc:
            logger.exception("Failed to create job %s in RDS", job_id)
            raise

    def get(self, job_id: str) -> dict[str, Any]:
        """Return a job by ID, or an empty dictionary if it does not exist."""
        try:
            with get_db_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id
                ).first()
                
                if not job:
                    return {}
                    
                return self._to_dict(job)
        except Exception as exc:
            logger.exception("Failed to retrieve job %s from RDS", job_id)
            return {}

    def update(self, job_id: str, **fields: Any) -> None:
        """Update fields on an existing job."""
        try:
            with get_db_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id
                ).first()
                
                if not job:
                    raise KeyError(f"Job not found: {job_id}")
                
                # Handle log appends
                if "log" in fields:
                    job.log = fields["log"]
                    del fields["log"]

                # Handle nested progress dict → flat columns
                if "progress" in fields:
                    prog = fields.pop("progress")
                    if isinstance(prog, dict):
                        job.progress_current = prog.get("current", job.progress_current)
                        job.progress_total = prog.get("total", job.progress_total)

                # Map service-level field names to DB column names
                field_map = {
                    "started": "started_at",
                    "completed": "completed_at",
                    "finished": "completed_at",
                    "error": "error_message",
                }

                for key, value in fields.items():
                    col_name = field_map.get(key, key)
                    if hasattr(job, col_name):
                        setattr(job, col_name, value)
                        
                session.commit()
        except KeyError:
            raise
        except Exception as exc:
            logger.exception("Failed to update job %s in RDS", job_id)
            raise

    def list_by_statuses(
        self,
        statuses: tuple[str, ...] | list[str],
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return jobs currently in any of `statuses`, oldest first.

        Used by the reconciler to find jobs the database still thinks are
        running. Oldest first so the longest-stranded are settled even when the
        limit truncates the sweep.
        """
        try:
            with get_db_session() as session:
                rows = (
                    session.query(Job)
                    .filter(Job.status.in_(tuple(statuses)))
                    # SQL Server's ORDER BY has no NULLS FIRST syntax.
                    .order_by(
                        case((Job.started_at.is_(None), 0), else_=1),
                        Job.started_at.asc(),
                    )
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "job_id": row.job_id,
                        "status": row.status,
                        "glue_job_run_id": row.glue_job_run_id,
                        "started_at": row.started_at,
                        "step": row.step,
                    }
                    for row in rows
                ]
        except Exception:
            logger.exception("Failed to list jobs by status")
            raise

    def transition(
        self,
        job_id: str,
        from_statuses: set[str],
        to_status: str,
        **fields: Any,
    ) -> bool:
        """Move a job to `to_status` only if it is currently in one of `from_statuses`.

        Returns True if this call performed the move, False if it did not - the
        job was already in some other state, or does not exist.

        This exists because read-then-write is not safe here. `start_draft_job`
        used to SELECT the job, check `status == 'draft'`, and then UPDATE it;
        two concurrent start requests could both pass the check before either
        wrote, and both would trigger a Glue run for the same job - two billed
        cluster runs writing results over each other. The status check and the
        write are one statement here, so the database decides the winner and the
        loser gets False.

        The same guard protects the terminal writes. Both the web tier and the
        Glue run write this row, so a late arrival can no longer resurrect a job
        that has already finished or been cancelled.
        """
        try:
            with get_db_session() as session:
                values: dict[str, Any] = {Job.status: to_status}

                field_map = {
                    "started": "started_at",
                    "completed": "completed_at",
                    "finished": "completed_at",
                    "error": "error_message",
                }

                for key, value in fields.items():
                    column_name = field_map.get(key, key)

                    if hasattr(Job, column_name):
                        values[getattr(Job, column_name)] = value

                changed = (
                    session.query(Job)
                    .filter(
                        Job.job_id == job_id,
                        Job.status.in_(tuple(from_statuses)),
                    )
                    .update(values, synchronize_session=False)
                )

                session.commit()

            if changed:
                logger.info(
                    "Job '%s' moved to '%s'",
                    job_id,
                    to_status,
                )
            else:
                # Not an error: the expected outcome whenever another writer got
                # there first, which is exactly what this method is for.
                logger.info(
                    "Job '%s' not moved to '%s'; it is no longer in %s",
                    job_id,
                    to_status,
                    sorted(from_statuses),
                )

            return bool(changed)
        except Exception:
            logger.exception(
                "Failed to transition job '%s' to '%s'",
                job_id,
                to_status,
            )
            raise

    def append_log(self, job_id: str, line: str) -> None:
        """Atomically append one line to a job's log.

        Done as a single `JSON_MODIFY(..., 'append $', ...)` UPDATE rather than
        read-append-write. Several writers touch one job's log concurrently -
        the status poller every 30s plus any request thread - and a
        read-modify-write holds no row lock, so two appends interleaving would
        silently drop one. `entry` is the raw line, not JSON-encoded:
        JSON_MODIFY's `append $` path adds it as one new string element.
        """

        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        "UPDATE jobs "
                        "SET log = JSON_MODIFY(COALESCE(log, '[]'), 'append $', :entry) "
                        "WHERE job_id = :job_id"
                    ),
                    {"job_id": job_id, "entry": line},
                )
                session.commit()

                if result.rowcount == 0:
                    raise KeyError(f"Job not found: {job_id}")
        except KeyError:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to append log for job %s", job_id
            )
            raise

    def exists(self, job_id: str) -> bool:
        """Return True if a job exists."""
        try:
            with get_db_session() as session:
                count = session.query(Job).filter(
                    Job.job_id == job_id
                ).count()
                return count > 0
        except Exception as exc:
            logger.error("Error checking existence for job %s: %s", job_id, exc)
            return False

    def list_page(
        self,
        owner: str | None = None,
        step: str = "",
        status: str = "",
        db_type: str = "",
        search: str = "",
        sort_by: str = "started",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of jobs plus the total matching count.

        Filtering, sorting and pagination all happen in SQL. The previous
        implementation loaded every job row into memory and sliced it in Python,
        which the V2 UI would hit every 1.4 seconds per open jobs list.
        Backed by idx_jobs_owner_step_status.
        """
        try:
            with get_db_session() as session:
                # The list needs the human-readable saved connection name and
                # type. Keep this an outer join so flat-file jobs and jobs whose
                # connection was later deleted are still visible.
                query = session.query(Job, SavedConnection.name, SavedConnection.db_type).outerjoin(
                    SavedConnection, Job.connection_id == SavedConnection.id
                )

                if owner is not None:
                    query = query.filter(Job.created_by == owner)

                if step:
                    query = query.filter(Job.step == str(step))

                if status:
                    query = query.filter(Job.status == status)

                if db_type == "flat_file":
                    # Flat-file jobs deliberately have no saved connection.
                    # `csv` is retained for drafts created by older clients.
                    query = query.filter(
                        func.JSON_VALUE(Job.params, "$.source_type").in_(("flat_file", "csv"))
                    )
                elif db_type:
                    # A job snapshots its database type at creation. Include it
                    # alongside the linked connection so filtering remains
                    # correct for legacy jobs and jobs whose connection was
                    # subsequently removed.
                    query = query.filter(
                        or_(
                            SavedConnection.db_type == db_type,
                            func.JSON_VALUE(Job.params, "$.databaseType") == db_type,
                        )
                    )

                if search:
                    pattern = f"%{search.strip().lower()}%"
                    query = query.filter(
                        or_(
                            func.lower(Job.job_id).like(pattern),
                            func.lower(func.coalesce(Job.name, "")).like(pattern),
                            func.lower(
                                func.coalesce(
                                    func.JSON_VALUE(Job.params, "$.project_name"), ""
                                )
                            ).like(pattern),
                        )
                    )

                total = query.count()

                column = {
                    "job_id": Job.job_id,
                    "status": Job.status,
                    "name": Job.name,
                }.get(sort_by, Job.started_at)

                query = query.order_by(
                    column.desc() if sort_order == "desc" else column.asc()
                )

                offset = max(page - 1, 0) * page_size
                rows = query.limit(page_size).offset(offset).all()

                return [
                    {
                        **self._to_dict(job),
                        "connection_name": connection_name,
                        "connection_db_type": connection_db_type,
                    }
                    for job, connection_name, connection_db_type in rows
                ], total
        except Exception:
            logger.exception("Failed to list jobs from RDS")
            raise

    def delete(self, job_id: str) -> bool:
        """Hard-delete a job and return whether it existed."""
        try:
            with get_db_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id
                ).first()
                
                if not job:
                    return False
                    
                session.delete(job)
                session.commit()
                return True
        except Exception as exc:
            logger.exception("Failed to delete job %s in RDS", job_id)
            return False
            
    def _to_dict(self, job: Job) -> dict[str, Any]:
        """Convert a Job SQLAlchemy model instance to a dictionary."""
        return {
            "job_id": str(job.job_id),
            "status": job.status,
            "params": job.params,
            "log": job.log,
            "report_path": job.report_path,
            "profile_path": job.profile_path,
            "staging_path": job.staging_path,
            "progress": {
                "current": job.progress_current or 0,
                "total": job.progress_total or 0,
            },
            "glue_job_run_id": job.glue_job_run_id,
            "started": job.started_at.isoformat() if job.started_at else None,
            "completed": job.completed_at.isoformat() if job.completed_at else None,
            "created_by": job.created_by,
            "error_message": job.error_message,
            "name": job.name,
            "description": job.description,
            "step": job.step,
            "connection_id": job.connection_id,
            "source_job_id": job.source_job_id,
        }
