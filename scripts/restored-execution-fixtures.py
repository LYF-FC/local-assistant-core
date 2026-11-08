"""Disposable restored no-op authority/lease quarantine CLI; no real external effect."""

import json
import subprocess
import sys
from uuid import UUID

import psycopg
from app import identity, jobs
from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "check", "container"}
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
approvals = {n: UUID(f"e1000000-1111-4111-8111-11111111111{n}") for n in range(1, 8)}
job_ids = {n: UUID(f"e2000000-1111-4111-8111-11111111111{n}") for n in range(3, 7)}
outbox = {n: UUID(f"e3000000-1111-4111-8111-11111111111{n}") for n in range(3, 7)}
old_token = "synthetic-restored-execution-lease-only-0123456789"
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
if phase in {"seed", "container"}:
    with psycopg.connect(url) as db:
        for n in range(1, 8):
            db.execute(
                "INSERT INTO public.approvals(id,scope_key,action_type,status,requested_by,request_payload,payload_hash,policy_version,requested_at,expires_at) VALUES(%s,%s,'validation.noop','pending',%s,'{\"note\":\"synthetic-execution-recovery-only\"}',repeat('b',64),'v0.1-record-only-1',clock_timestamp(),clock_timestamp()+interval '1 hour')",
                (
                    approvals[n],
                    "finance_private" if n == 7 else "household_shared",
                    str(actor),
                ),
            )
            if 2 <= n <= 6:
                db.execute(
                    "UPDATE public.approvals SET status='approved',approved_by=%s,resolved_at=clock_timestamp() WHERE id=%s",
                    (actor, approvals[n]),
                )
            if 3 <= n <= 6:
                db.execute(
                    "UPDATE public.approvals SET status='consumed',consumed_at=clock_timestamp() WHERE id=%s",
                    (approvals[n],),
                )
                status = "running" if n == 4 else "succeeded" if n == 5 else "queued"
                db.execute(
                    "INSERT INTO public.durable_jobs(id,approval_id,requested_by,scope_key,action_type,payload_hash,idempotency_hash,status,created_at,result_code,finished_at) VALUES(%s,%s,%s,'household_shared','validation.noop',repeat('b',64),%s,%s,clock_timestamp(),%s,CASE WHEN %s THEN clock_timestamp() ELSE NULL END)",
                    (
                        job_ids[n],
                        approvals[n],
                        actor,
                        str(n) * 64,
                        status,
                        "noop_completed" if n == 5 else None,
                        n == 5,
                    ),
                )
                db.execute(
                    "INSERT INTO public.job_outbox(id,job_id,state,attempts,available_at,lease_hash,lease_until) VALUES(%s,%s,%s,%s,clock_timestamp(),%s,CASE WHEN %s THEN clock_timestamp()+interval '1 hour' ELSE NULL END)",
                    (
                        outbox[n],
                        job_ids[n],
                        "leased" if n == 4 else "done" if n == 5 else "pending",
                        1 if n in {4, 5} else 0,
                        identity.digest(old_token) if n == 4 else None,
                        n == 4,
                    ),
                )


def command(*args, success=True):
    base = [
        sys.executable,
        "-m",
        "app.restore_execution",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(actor),
        "--scope",
        "household_shared",
    ]
    for n in (1, 2):
        base += ["--approval", str(approvals[n])]
    for n in (3, 4, 5):
        base += ["--job", str(job_ids[n])]
    result = subprocess.run([*base, *args], capture_output=True, text=True, check=False)
    assert (result.returncode == 0) == success, (
        "Synthetic restored-execution CLI failed"
    )
    if success:
        return json.loads(result.stdout)
    assert not result.stdout and "inspect metadata/receipt" in result.stderr


if phase != "seed":
    with psycopg.connect(url) as db:
        before_approvals = db.execute(
            "SELECT * FROM public.approvals WHERE NOT(id=ANY(%s)) ORDER BY id",
            ([approvals[1], approvals[2]],),
        ).fetchall()
        before_jobs = db.execute(
            "SELECT * FROM public.durable_jobs WHERE NOT(id=ANY(%s)) ORDER BY id",
            ([job_ids[3], job_ids[4]],),
        ).fetchall()
        before_outbox = db.execute(
            "SELECT * FROM public.job_outbox WHERE NOT(job_id=ANY(%s)) ORDER BY id",
            ([job_ids[3], job_ids[4]],),
        ).fetchall()
        assert (
            db.execute(
                "SELECT status FROM public.durable_jobs WHERE id=%s", (job_ids[4],)
            ).fetchone()[0]
            == "running"
        )
    plan = command()
    assert (
        len(plan["items"]) == 5
        and sum(item["changes_required"] for item in plan["items"]) == 4
    )
    assert (
        "lease_hash" not in json.dumps(plan)
        and "payload_hash" not in json.dumps(plan)
        and old_token not in json.dumps(plan)
    )
    args = (
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "quarantine_restored_execution",
    )
    result = command(*args)
    command(*args, success=False)
    assert not result["dispatch_activated"] and not result["recovery_complete"]
    with psycopg.connect(url) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.approvals WHERE id=ANY(%s) AND status='cancelled'",
                ([approvals[1], approvals[2]],),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.durable_jobs WHERE id=ANY(%s) AND status='dead_letter' AND result_code='restore_quarantined'",
                ([job_ids[3], job_ids[4]],),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.job_outbox WHERE job_id=ANY(%s) AND state='dead_letter' AND lease_hash IS NULL AND lease_until IS NULL",
                ([job_ids[3], job_ids[4]],),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT * FROM public.approvals WHERE NOT(id=ANY(%s)) ORDER BY id",
                ([approvals[1], approvals[2]],),
            ).fetchall()
            == before_approvals
        )
        assert (
            db.execute(
                "SELECT * FROM public.durable_jobs WHERE NOT(id=ANY(%s)) ORDER BY id",
                ([job_ids[3], job_ids[4]],),
            ).fetchall()
            == before_jobs
        )
        assert (
            db.execute(
                "SELECT * FROM public.job_outbox WHERE NOT(job_id=ANY(%s)) ORDER BY id",
                ([job_ids[3], job_ids[4]],),
            ).fetchall()
            == before_outbox
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (result["receipt_id"],),
            ).fetchone()[0]
            == result
        )
    engine = create_engine(settings.database_url)
    with Session(engine) as db, db.begin():
        assert not jobs.finish(db, jobs.Claim(outbox[4], old_token))
    engine.dispose()
print(
    "Synthetic restored-execution fixture seeded; no payloads/tokens displayed"
    if phase == "seed"
    else "Synthetic restored-execution cancellation/dead-letter/old-lease/receipt/control preservation verified; no payloads/tokens displayed"
)
