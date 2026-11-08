"""Trusted local synthetic parties; no API dependency, user grant or real directory."""

import argparse
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import work_lifecycle
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target


class Party(work_lifecycle.Contract):
    workspace_id: UUID
    id: UUID
    policy_id: UUID
    revision: int = Field(strict=True, ge=1, le=3)
    state: Literal["active", "retired", "forgotten"]
    marker: work_lifecycle.Marker | None = Field(repr=False)
    retain_until: datetime
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def coherent(self):
        if (self.state == "forgotten") != (self.marker is None):
            raise ValueError("Forgotten party label must be redacted")
        if not work_lifecycle.clock(self.created_at) <= work_lifecycle.clock(self.updated_at):
            raise ValueError("Invalid party time")
        if work_lifecycle.clock(self.retain_until) <= work_lifecycle.clock(self.created_at):
            raise ValueError("Invalid party retention")
        return self


def _begin(db, workspace_id, *, maintenance=False, restore=False):
    validate_target(settings.env)
    if (
        type(maintenance) is not bool
        or type(restore) is not bool
        or (maintenance and restore)
        or not isinstance(workspace_id, UUID)
        or db.info.transaction_status != TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local party transaction required")
    if db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),current_user=pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.parties'::regclass"
    ).fetchone() != (True, "read committed", True):
        raise ValueError("Clean local party storage owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    if restore:
        db.execute("SET LOCAL butler.restore_suppression='reviewed'")
        if not db.execute(
            "SELECT work.restore_suppression_allowed(%s)", (workspace_id,)
        ).fetchone()[0]:
            raise ValueError("Quarantined restore required")
    if maintenance:
        db.execute("SET LOCAL butler.retention_cleanup='expired'")
    if not db.execute(
        "SELECT 1 FROM public.work_workspaces WHERE id=%s AND is_active=%s AND slug LIKE 'synthetic-%%'",
        (workspace_id, not (maintenance or restore)),
    ).fetchone():
        raise ValueError("Active synthetic workspace required")


def _result(db, query, values):
    with db.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(query, values).fetchone()
    if row is None:
        raise ValueError("Party unavailable or stale revision")
    result = Party.model_validate(row)
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),clock_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin','admin.work_party_changed','work_access_registry',%s,'success','{}',%s)",
        (
            settings.env,
            str(result.workspace_id),
            Jsonb({"party_id": str(result.id), "revision": result.revision, "state": result.state}),
        ),
    )
    return result


def create(db, workspace_id: UUID, policy_id: UUID, marker: str, retain_until: datetime):
    # Validate before database use and keep all free text synthetic.
    from pydantic import TypeAdapter

    marker = TypeAdapter(work_lifecycle.Marker).validate_python(marker)
    retain_until = work_lifecycle.clock(retain_until)
    if not isinstance(policy_id, UUID):
        raise TypeError("Typed retention policy required")
    _begin(db, workspace_id)
    return _result(
        db,
        "INSERT INTO work.parties(workspace_id,id,policy_id,revision,state,marker,retain_until) VALUES(%s,%s,%s,1,'active',%s,%s) RETURNING *",
        (workspace_id, uuid4(), policy_id, marker, retain_until),
    )


def transition(
    db,
    workspace_id: UUID,
    party_id: UUID,
    expected_revision: int,
    action: str,
    *,
    maintenance=False,
    restore=False,
):
    if (
        not isinstance(party_id, UUID)
        or type(expected_revision) is not int
        or not 1 <= expected_revision <= 2
        or action not in {"retire", "forget"}
    ):
        raise ValueError("Typed party and explicit terminal transition required")
    if (maintenance or restore) and action != "forget":
        raise ValueError("Maintenance only forgets expired parties")
    _begin(db, workspace_id, maintenance=maintenance, restore=restore)
    if (
        maintenance
        and not db.execute(
            "SELECT 1 FROM work.parties WHERE workspace_id=%s AND id=%s AND state<>'forgotten' AND retain_until<=clock_timestamp()",
            (workspace_id, party_id),
        ).fetchone()
    ):
        raise ValueError("Maintenance requires an expired party")
    state = "retired" if action == "retire" else "forgotten"
    return _result(
        db,
        "UPDATE work.parties SET state=%s,revision=revision+1,marker=CASE WHEN %s='forgotten' THEN NULL ELSE marker END WHERE workspace_id=%s AND id=%s AND revision=%s AND state<>'forgotten' RETURNING *",
        (state, state, workspace_id, party_id, expected_revision),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", type=UUID, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    new = sub.add_parser("create")
    new.add_argument("--policy", type=UUID, required=True)
    new.add_argument("--marker", required=True)
    new.add_argument("--retain-until", type=datetime.fromisoformat, required=True)
    for action in ("retire", "forget"):
        command = sub.add_parser(action)
        command.add_argument("--party", type=UUID, required=True)
        command.add_argument("--expected-revision", type=int, required=True)
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            party = (
                create(db, args.workspace, args.policy, args.marker, args.retain_until)
                if args.action == "create"
                else transition(db, args.workspace, args.party, args.expected_revision, args.action)
            )
    except (psycopg.Error, ValueError):
        parser.exit(1, "Synthetic party operation failed; transaction rolled back\n")
    print(f"Synthetic party {party.id}; revision {party.revision}; state {party.state}")


if __name__ == "__main__":
    main()
