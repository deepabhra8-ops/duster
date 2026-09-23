from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_db_session
from repositories.models import Job, ValidationResult


SEED_TAG = "[demo data]"

DEFAULT_USER = "admin"
DEFAULT_COUNT = 50
TREND_DAYS = 7

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

SOURCES = [
    ("MySQL", "mysql"),
    ("Postgres", "postgresql"),
    ("Redshift", "redshift"),
    ("Salesforce", "salesforce"),
    ("Snowflake", "snowflake"),
]

STATUS_WEIGHTS = [("done", 74), ("error", 13), ("cancelled", 6), ("draft", 5), ("queued", 2)]

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
    jobs: list[Job] = []
    results: list[ValidationResult] = []

    now = datetime.utcnow()

    day_baseline = {
        offset: 0.965 - (TREND_DAYS - 1 - offset) * 0.012
        for offset in range(TREND_DAYS)
    }

    for index in range(count):
        schema, table, label = rng.choice(SUBJECTS)
        source, db_type = rng.choice(SOURCES)
        is_validation = rng.random() < 0.45
        status = _weighted_status(rng)

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

    validations = sum(1 for job in jobs if job.step == "3")

    with get_db_session() as session:
        session.add_all(jobs)
        session.flush()
        session.add_all(results)
        session.commit()

    print(
        f"Inserted {len(jobs)} demo jobs for '{user}' "
        f"({validations} validation, {len(jobs) - validations} profiling), "
        f"{len(results)} with scores, across the last {TREND_DAYS} days."
    )
    print(f"Remove them with: python {Path(__file__).name} --remove --user {user}")


def remove(user: str) -> None:
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

        session.query(ValidationResult).filter(
            ValidationResult.job_id.in_(job_ids)
        ).delete(synchronize_session=False)
        session.query(Job).filter(Job.job_id.in_(job_ids)).delete(
            synchronize_session=False
        )
        session.commit()

    print(f"Removed {len(job_ids)} demo jobs for '{user}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed realistic demo jobs so the dashboard has something to show.")
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
