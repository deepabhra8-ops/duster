"""Seed realistic demo jobs so the dashboard has something to show.

An empty dashboard cannot be reviewed: every tile reads 0, the trend line has no
points, and the Jobs-by-Type bars have no lengths to compare. This writes a week
of plausible history - profiling and validation runs over real-looking source
tables, with the statuses a real week produces - so the layout, the charts and
the 7-day trend window can all be judged against something.

It is demo data and it says so. Every row it writes is tagged (see SEED_TAG),
which is the only thing that makes the cleanup exact:

    python scripts/seed_dashboard_demo.py            # insert
    python scripts/seed_dashboard_demo.py --remove   # delete exactly what it inserted
    python scripts/seed_dashboard_demo.py --count 80 --user alice

Nothing else in the database is touched, and removal never deletes a row this
script did not create.

Deliberately NOT written here: the large `params` blob a real job carries (it
holds a source config, and a fabricated one would be a config that cannot run)
and a full findings `summary`. `validation_results.summary` is NOT NULL, so
validation rows get a small, honest rollup - the score and per-dimension figures
the job page actually reads - rather than an invented findings list.
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Run as a plain script from backend/: `python scripts/seed_dashboard_demo.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_db_session  # noqa: E402
from repositories.models import Job, ValidationResult  # noqa: E402


# Written into every seeded row's description. It is the handle `--remove` uses,
# and it is visible in the UI on purpose: a demo row should admit to being one.
SEED_TAG = "[demo data]"

DEFAULT_USER = "admin"
DEFAULT_COUNT = 50
TREND_DAYS = 7

# Realistic subjects for a data-quality tool: a claims warehouse, a CRM feed and
# a marketing/donation staging area - the kinds of tables these runs profile.
SUBJECTS = [
    ("claims", "claim_header", "Claims"),
    ("claims", "claim_line", "Claim lines"),
    ("claims", "claim_adjustment", "Claim adjustments"),
    ("claims", "provider", "Providers"),
    ("claims", "member_eligibility", "Member eligibility"),
    ("crm", "account", "Salesforce accounts"),
    ("crm", "contact", "Salesforce contacts"),
    ("crm", "opportunity", "Opportunities"),
    ("crm", "account_contact_relation", "Account/contact relations"),
    ("finance", "payment", "Payments"),
    ("finance", "invoice_line", "Invoice lines"),
    ("finance", "gl_transaction", "GL transactions"),
    ("staging", "stg_donation_behavior_modeling", "Donation behaviour model input"),
    ("staging", "stg_donor_contact_history", "Donor contact history"),
    ("staging", "stg_campaign_response", "Campaign responses"),
    ("reference", "diagnosis_code", "Diagnosis code reference"),
    ("reference", "procedure_code", "Procedure code reference"),
    ("reference", "state_lookup", "State lookup"),
]

# (display name, the `databaseType` value the UI maps to a label). The value is
# what the jobs lists read for their Type column - DATABASE_TYPE_OPTIONS in
# sourceTypes.js maps it back to "MySQL", "PostgreSQL" and so on. Left unset it
# serialised as "", which the lookup resolved to the dropdown's own placeholder,
# so every seeded row's Type read "- Select database type -".
SOURCES = [
    ("MySQL", "mysql"),
    ("Postgres", "postgresql"),
    ("Redshift", "redshift"),
    ("Salesforce", "salesforce"),
    ("Snowflake", "snowflake"),
]

# Roughly what a working week produces: mostly finished runs, a handful of
# failures, the occasional cancelled one and a draft left open. Weighted rather
# than uniform, so the Jobs-by-Type bars have a realistic shape instead of four
# equal blocks.
STATUS_WEIGHTS = [("done", 74), ("error", 13), ("cancelled", 6), ("draft", 5), ("queued", 2)]

# A real failure names a cause. These are the causes this project actually hits.
ERRORS = [
    "cannot import name 'DBAPIModule' from 'sqlalchemy.engine.interfaces'\n"
    "(/home/hadoop/.local/lib/python3.11/site-packages/sqlalchemy/engine/interfaces.py)",
    "py4j.protocol.Py4JJavaError: An error occurred while calling o142.load.\n"
    ": java.sql.SQLException: [Amazon](500310) Invalid operation: "
    'relation "public.claim_adjustment" does not exist;',
    "GlueJobRunFailed: the job run timed out after 60 minutes.",
    "botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling "
    "the GetObject operation: Access Denied",
    "salesforce.exceptions.SalesforceAuthenticationFailed: INVALID_LOGIN: "
    "Invalid username, password, security token; or user locked out.",
]

DIMENSIONS = ["Completeness", "Conformity", "Uniqueness", "Consistency"]


def _weighted_status(rng: random.Random) -> str:
    population = [status for status, _ in STATUS_WEIGHTS]
    weights = [weight for _, weight in STATUS_WEIGHTS]
    return rng.choices(population, weights=weights, k=1)[0]


def _summary(rng: random.Random, score: float) -> dict:
    """The small rollup a validation job's page reads - not a findings dump."""
    return {
        "overall_score": round(score, 4),
        "dimensions": {
            name: round(min(1.0, max(0.0, score + rng.uniform(-0.06, 0.06))), 4)
            for name in DIMENSIONS
        },
        "not_run_count": rng.choice([0, 0, 0, 3, 8, 33]),
        "sheets": {},
    }


def _build_rows(count: int, user: str, rng: random.Random):
    """Return (jobs, results) to insert, spread across the trend window."""
    jobs: list[Job] = []
    results: list[ValidationResult] = []

    now = datetime.utcnow()

    # A gentle downward drift across the week, so the trend line has a shape to
    # read rather than noise around a flat mean.
    day_baseline = {
        offset: 0.965 - (TREND_DAYS - 1 - offset) * 0.012
        for offset in range(TREND_DAYS)
    }

    for index in range(count):
        schema, table, label = rng.choice(SUBJECTS)
        source, db_type = rng.choice(SOURCES)
        is_validation = rng.random() < 0.45
        status = _weighted_status(rng)

        # Spread over the last 7 days, business-hours-ish, newest day included.
        days_ago = rng.randint(0, TREND_DAYS - 1)
        started = (now - timedelta(days=days_ago)).replace(
            hour=rng.randint(8, 18),
            minute=rng.randint(0, 59),
            second=rng.randint(0, 59),
            microsecond=0,
        )
        if started > now:
            started = now - timedelta(minutes=rng.randint(5, 240))

        job_id = str(uuid.uuid4())
        kind = "Validation" if is_validation else "Profile"
        name = f"{kind} - {table} ({source})"[:255]
        description = f"{SEED_TAG} {label} from {source}, {schema}.{table}."

        completed = None
        if status in ("done", "error", "cancelled"):
            completed = started + timedelta(minutes=rng.randint(2, 47))

        job = Job(
            job_id=job_id,
            status=status,
            # Only the two display fields the jobs lists read, so the Type
            # column resolves to a real label. Still no fabricated source
            # config - see the module docstring on why a made-up host and
            # credential set would be worse than none.
            params={"databaseType": db_type, "source_type": "database"},
            log=[],
            progress_current=100 if status == "done" else 0,
            progress_total=100,
            started_at=started,
            completed_at=completed,
            created_by=user,
            error_message=rng.choice(ERRORS) if status == "error" else None,
            name=name,
            description=description,
            step="3" if is_validation else "1",
        )
        jobs.append(job)

        # Only finished validation runs produce a score - which is exactly what
        # makes the trend line's gaps honest.
        if is_validation and status == "done":
            score = min(0.999, max(0.72, rng.gauss(day_baseline[days_ago], 0.025)))
            results.append(
                ValidationResult(
                    job_id=job_id,
                    overall_score=round(score, 4),
                    summary=_summary(rng, score),
                    created_at=completed or started,
                )
            )

    return jobs, results


def insert(count: int, user: str, seed: int | None) -> None:
    rng = random.Random(seed)
    jobs, results = _build_rows(count, user, rng)

    # Counted BEFORE the insert: committing expires every attribute on these
    # instances, and reading one back outside the session raises
    # DetachedInstanceError rather than returning the value.
    validations = sum(1 for job in jobs if job.step == "3")

    with get_db_session() as session:
        session.add_all(jobs)
        session.flush()          # jobs must exist before the FK rows
        session.add_all(results)
        session.commit()

    print(
        f"Inserted {len(jobs)} demo jobs for '{user}' "
        f"({validations} validation, {len(jobs) - validations} profiling), "
        f"{len(results)} with scores, across the last {TREND_DAYS} days."
    )
    print(f"Remove them with: python {Path(__file__).name} --remove --user {user}")


def remove(user: str) -> None:
    """Delete only the rows this script wrote, identified by the tag."""
    with get_db_session() as session:
        seeded = (
            session.query(Job.job_id)
            .filter(Job.created_by == user)
            .filter(Job.description.like(f"{SEED_TAG}%"))
            .all()
        )
        job_ids = [row[0] for row in seeded]

        if not job_ids:
            print(f"No demo rows found for '{user}'. Nothing to remove.")
            return

        # validation_results is ON DELETE CASCADE, but delete explicitly rather
        # than relying on it - this must work the same on a database where the
        # constraint was created without the cascade.
        session.query(ValidationResult).filter(
            ValidationResult.job_id.in_(job_ids)
        ).delete(synchronize_session=False)
        session.query(Job).filter(Job.job_id.in_(job_ids)).delete(
            synchronize_session=False
        )
        session.commit()

    print(f"Removed {len(job_ids)} demo jobs for '{user}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", default=DEFAULT_USER, help="Job owner (default: admin)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Jobs to insert")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed, for repeatable data")
    parser.add_argument("--remove", action="store_true", help="Delete this script's rows")
    args = parser.parse_args()

    if args.remove:
        remove(args.user)
    else:
        insert(args.count, args.user, args.seed)


if __name__ == "__main__":
    main()
