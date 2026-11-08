"""Explicit local synthetic review provisioning; never called by API startup."""

import argparse

import psycopg
from psycopg import sql

from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target
from app.work_storage import provision


def provision_reviews(connection, workspace_slug: str) -> None:
    validate_target(settings.env)
    connection.execute("SET LOCAL lock_timeout='2s'")
    connection.execute("SET LOCAL statement_timeout='5s'")
    connection.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    role = sql.Identifier(provision(connection, workspace_slug))
    connection.execute(
        sql.SQL("GRANT SELECT ON work.drafts,work.source_registry,work.draft_reviews TO {}").format(
            role
        )
    )
    # Row locks require UPDATE on a column. Every actual id/noop mutation is
    # rejected by the existing draft revision/identity guard; no payload grant.
    connection.execute(sql.SQL("GRANT UPDATE(id) ON work.drafts TO {}").format(role))
    connection.execute(
        sql.SQL(
            "GRANT INSERT(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) ON work.draft_reviews TO {}"
        ).format(role)
    )
    connection.execute(
        sql.SQL(
            "GRANT INSERT(workspace_id,record_id,revision,actor_id,event_type) ON work.draft_audit TO {}"
        ).format(role)
    )
    connection.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),statement_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin','admin.work_review_provisioned','success','{}','{}')",
        (settings.env,),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    validate_target(args.environment)
    try:
        with psycopg.connect(
            settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
        ) as db:
            provision_reviews(db, args.workspace)
    except (psycopg.Error, ValueError):
        parser.exit(1, "Synthetic review provisioning failed; no application writer enabled\n")
    print("Synthetic review privileges provisioned; explicit adapter/review opt-in still required")


if __name__ == "__main__":
    main()
