"""Explicit local note-change preparation grants; no API note mutation."""

import argparse

import psycopg
from psycopg import sql

from app.config import settings
from app.work_capture_storage import provision_captures
from app.work_credentials import validate_target
from app.work_storage import role_name


def provision_changes(db, slug):
    validate_target(settings.env)
    provision_captures(db, slug)
    workspace = db.execute(
        "SELECT id FROM public.work_workspaces WHERE slug=%s", (slug,)
    ).fetchone()[0]
    oid = db.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[0]
    role = sql.Identifier(role_name(oid, workspace))
    db.execute(sql.SQL("GRANT SELECT ON work.note_metadata TO {}").format(role))
    db.execute(
        sql.SQL(
            "GRANT INSERT(intent,target_record_id,expected_revision) ON work.capture_intents TO {}"
        ).format(role)
    )
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),clock_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin','admin.work_note_changes_provisioned','work_access_registry',%s,'success','{}','{}')",
        (settings.env, str(workspace)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        with psycopg.connect(
            settings.database_url.replace("postgresql+psycopg", "postgresql", 1), connect_timeout=3
        ) as db:
            provision_changes(db, args.workspace)
    except (psycopg.Error, ValueError):
        parser.exit(1, "Synthetic note-change provisioning failed; no note writer enabled\n")
    print("Synthetic note changes prepared; explicit adapter/change opt-in still required")


if __name__ == "__main__":
    main()
