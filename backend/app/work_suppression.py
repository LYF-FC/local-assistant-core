"""Reviewed synthetic forgetting reconciliation; no latest-ledger/recovery certificate."""

import argparse
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import (
    work_confirmation_worker,
    work_drafts,
    work_lifecycle,
    work_notes_worker,
    work_parties,
)
from app import work_suppression_auth as authentication
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target
from app.work_suppression_file import Body, Manifest, canonical, digest


class Request(work_lifecycle.Contract):
    workspace_id: UUID
    operator_id: UUID
    database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    decision: Literal["export", "preview", "reconcile_restored_suppressions"] = "preview"
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    expected_manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    auth_key_id: UUID | None = None
    auth_key_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid(self):
        if (self.auth_key_id is None) != (self.auth_key_fingerprint is None):
            raise ValueError("Complete authentication reference required")
        if self.decision == "export" and self.expected_manifest_hash is not None:
            raise ValueError("Source export cannot carry target checkpoint")
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "reconcile_restored_suppressions":
            if self.issued_at is None or self.reviewed_hash is None:
                raise ValueError("Explicit current reviewed plan required")
        elif self.reviewed_hash is not None or (
            self.decision == "export" and self.issued_at is not None
        ):
            raise ValueError("Export/preview cannot carry apply authority")
        return self


def _begin(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.work_workspaces'::regclass,'public.work_access_grants'::regclass,'public.users'::regclass,'public.audit_events'::regclass,'work.drafts'::regclass,'work.parties'::regclass,'work.capture_intents'::regclass,'work.draft_reviews'::regclass,'public.work_confirmation_requests'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 9):
        raise ValueError("Clean local storage/registry/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    if not db.execute(
        "SELECT 1 FROM public.work_workspaces WHERE id=%s AND NOT is_active AND slug LIKE 'synthetic-%%' FOR UPDATE",
        (request.workspace_id,),
    ).fetchone():
        raise ValueError("Disabled synthetic workspace required")
    if (
        request.decision != "export"
        and db.execute(
            "SELECT 1 FROM public.work_access_grants WHERE workspace_id=%s LIMIT 1",
            (request.workspace_id,),
        ).fetchone()
    ):
        raise ValueError("Quarantined no-grant restore required")
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    if not db.execute(
        "SELECT to_regprocedure('work.restore_suppression_allowed(uuid)') IS NOT NULL"
    ).fetchone()[0]:
        raise ValueError("Suppression migration required")
    return target


def _authentication(request):
    if request.auth_key_id is None:
        return {"mode": "trusted_owner_input"}
    return {
        "mode": "hmac_sha256",
        "key_id": str(request.auth_key_id),
        "key_fingerprint": request.auth_key_fingerprint,
    }


def _audit(db, request, event, result):
    receipt = uuid4()
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_work_suppression','technical_admin',%s,'work_access_registry',%s,'success','{}',%s)",
        (
            receipt,
            settings.env,
            event,
            str(request.workspace_id),
            Jsonb({**result, "receipt_id": str(receipt)}),
        ),
    )
    return str(receipt)


def prepare(db, request: Request):
    target = _begin(db, request)
    if request.decision != "export":
        raise ValueError("Explicit export required")
    rows = db.execute(
        """SELECT * FROM (
      SELECT 'note' AS kind,d.id,d.revision,t.forgotten_at FROM work.drafts d LEFT JOIN work.draft_tombstones t ON t.workspace_id=d.workspace_id AND t.record_id=d.id AND t.revision=d.revision WHERE d.workspace_id=%s AND d.state='forgotten'
      UNION ALL SELECT 'party',p.id,p.revision,a.occurred_at FROM work.parties p LEFT JOIN work.party_audit a ON a.workspace_id=p.workspace_id AND a.party_id=p.id AND a.revision=p.revision AND a.event_type='party.forgotten' WHERE p.workspace_id=%s AND p.state='forgotten'
    ) decisions ORDER BY kind,id LIMIT 26""",
        (request.workspace_id, request.workspace_id),
    ).fetchall()
    if len(rows) > 25 or any(row[3] is None for row in rows):
        raise ValueError("Too many or inconsistent terminal decisions; no partial manifest")
    body = Body(
        export_id=uuid4(),
        workspace_id=request.workspace_id,
        exported_by=request.operator_id,
        source_database_oid=target[1],
        generated_at=work_drafts._now(db),
        items=tuple(
            {"kind": row[0], "id": row[1], "forgotten_revision": row[2], "forgotten_at": row[3]}
            for row in rows
        ),
    )
    manifest = Manifest(body=body, digest=digest(body))
    _audit(
        db,
        request,
        "admin.work_suppression_manifest_prepared",
        {
            "export_id": str(body.export_id),
            "manifest_hash": manifest.digest,
            "item_count": len(body.items),
            "operator_id": str(request.operator_id),
            "saved_file_proven": False,
            "authentication_requested": _authentication(request),
        },
    )
    return manifest


def _fresh(db, issued):
    now = work_drafts._now(db)
    if not now - timedelta(minutes=5) <= issued <= now:
        raise ValueError("Use a current server-issued plan")


def _plan(db, request, manifest):
    target = _begin(db, request)
    if (
        request.decision == "export"
        or not isinstance(manifest, Manifest)
        or manifest.body.workspace_id != request.workspace_id
    ):
        raise ValueError("Matching typed workspace manifest required")
    context = (
        {"mode": "trusted_owner_input"}
        if request.expected_manifest_hash is None
        else authentication.require_checkpoint(manifest, request.expected_manifest_hash)
    )
    now = work_drafts._now(db)
    if work_lifecycle.clock(manifest.body.generated_at) > now:
        raise ValueError("Future manifest cannot be reconciled")
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else now
    _fresh(db, issued)
    items = []
    linked_count = 0
    for entry in manifest.body.items:
        if entry.kind == "note":
            current = db.execute(
                "SELECT state,revision FROM work.drafts WHERE workspace_id=%s AND id=%s",
                (request.workspace_id, entry.id),
            ).fetchone()
            links = db.execute(
                """SELECT * FROM (
              SELECT 'change' AS kind,id,expires_at FROM work.capture_intents WHERE workspace_id=%s AND target_record_id=%s AND state='pending'
              UNION ALL SELECT 'confirmation',id,expires_at FROM public.work_confirmation_requests WHERE workspace_id=%s AND record_id=%s AND state='pending'
              UNION ALL SELECT 'review',id,expires_at FROM work.draft_reviews WHERE workspace_id=%s AND record_id=%s AND payload_hash IS NOT NULL
            ) links ORDER BY kind,id LIMIT 101""",
                (request.workspace_id, entry.id) * 3,
            ).fetchall()
        else:
            current = db.execute(
                "SELECT state,revision FROM work.parties WHERE workspace_id=%s AND id=%s",
                (request.workspace_id, entry.id),
            ).fetchone()
            links = []
        linked_count += len(links)
        if linked_count > 100:
            raise ValueError("Too many linked effects; no partial reconciliation")
        if current and current[0] != "forgotten" and current[1] >= entry.forgotten_revision:
            raise ValueError("Live target conflicts with terminal source revision")
        items.append(
            {
                "kind": entry.kind,
                "id": str(entry.id),
                "source_revision": entry.forgotten_revision,
                "state": current[0] if current else "absent",
                "revision": current[1] if current else None,
                "linked": [
                    {"kind": row[0], "id": str(row[1]), "expires_at": row[2].isoformat()}
                    for row in links
                ],
                "changes_required": bool(links) or bool(current and current[0] != "forgotten"),
            }
        )
    plan = {
        "schema_version": 1,
        "mode": "synthetic_work_suppression_plan",
        "checkpoint": context,
        "database": target[0],
        "database_oid": target[1],
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "manifest_hash": manifest.digest,
        "export_id": str(manifest.body.export_id),
        "manifest_generated_at": manifest.body.generated_at.isoformat(),
        "authentication": _authentication(request),
        "issued_at": issued.isoformat(),
        "items": items,
        "linked_count": linked_count,
        "workspace_enabled": False,
        "work_grants": 0,
        "recovery_complete": False,
    }
    result = {
        **plan,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.work-suppression-plan.v1\n" + canonical(plan)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Plan exceeds metadata byte bound")
    return result


def reconcile(db, request: Request, manifest: Manifest):
    """Caller commits; prepared result never enables/regrants Work."""
    plan = _plan(db, request, manifest)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not any(item["changes_required"] for item in plan["items"]):
        raise ValueError("No changes to reconcile; no completion receipt")
    for item in plan["items"]:
        identifier = UUID(item["id"])
        if item["state"] not in {"absent", "forgotten"}:
            if item["kind"] == "note":
                work_drafts.transition(
                    db,
                    request.workspace_id,
                    request.operator_id,
                    identifier,
                    item["revision"],
                    "forget",
                    restore=True,
                )
            else:
                work_parties.transition(
                    db, request.workspace_id, identifier, item["revision"], "forget", restore=True
                )
        for link in item["linked"]:
            if link["kind"] == "change":
                row = work_notes_worker._one(
                    db,
                    "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND id=%s FOR UPDATE",
                    (request.workspace_id, UUID(link["id"])),
                )
                if row["state"] == "pending":
                    work_notes_worker._finish(db, row, "forgotten")
            elif link["kind"] == "confirmation":
                row = work_confirmation_worker._one(
                    db,
                    "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=%s AND id=%s FOR UPDATE",
                    (request.workspace_id, UUID(link["id"])),
                )
                if row["state"] == "pending":
                    work_confirmation_worker._finish(db, row, reason="stale")
            elif db.execute(
                "SELECT 1 FROM work.draft_reviews WHERE workspace_id=%s AND id=%s AND payload_hash IS NOT NULL",
                (request.workspace_id, UUID(link["id"])),
            ).fetchone():
                raise ValueError("Review redaction invariant failed; roll back")
    result = {
        "schema_version": 1,
        "mode": "synthetic_work_suppression_applied",
        "checkpoint": plan["checkpoint"],
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "manifest_hash": manifest.digest,
        "authentication": _authentication(request),
        "export_id": str(manifest.body.export_id),
        "manifest_generated_at": manifest.body.generated_at.isoformat(),
        "plan_hash": plan["reviewed_hash"],
        "outcomes": [
            {
                "kind": item["kind"],
                "id": item["id"],
                "previous_state": item["state"],
                "linked_effects": len(item["linked"]),
            }
            for item in plan["items"]
        ],
        "workspace_enabled": False,
        "work_grants": 0,
        "recovery_complete": False,
    }
    receipt = _audit(db, request, "admin.work_suppression_applied", result)
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return {**result, "receipt_id": receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--database", required=True)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--recovery-key", required=True)
    parser.add_argument("--expected-key-fingerprint", required=True)
    parser.add_argument("--expected-manifest-hash")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--output", required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("--manifest", required=True)
    preview.add_argument("--issued-at", type=datetime.fromisoformat)
    apply = commands.add_parser("apply")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--issued-at", type=datetime.fromisoformat, required=True)
    apply.add_argument("--reviewed-hash", required=True)
    apply.add_argument("--decision", required=True, choices=["reconcile_restored_suppressions"])
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        decision = (
            "export"
            if args.command == "export"
            else ("preview" if args.command == "preview" else args.decision)
        )
        key = authentication.load_key(
            args.recovery_key, args.expected_key_fingerprint, args.workspace
        )
        request = Request(
            workspace_id=args.workspace,
            operator_id=args.operator,
            database=args.database,
            decision=decision,
            issued_at=getattr(args, "issued_at", None),
            reviewed_hash=getattr(args, "reviewed_hash", None),
            expected_manifest_hash=args.expected_manifest_hash,
            auth_key_id=key.key_id,
            auth_key_fingerprint=authentication.fingerprint(key),
        )
        manifest = (
            None
            if args.command == "export"
            else authentication.read_signed(args.manifest, key, args.workspace)
        )
        if manifest is not None:
            authentication.require_checkpoint(manifest, args.expected_manifest_hash)
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            result = (
                prepare(db, request)
                if args.command == "export"
                else reconcile(db, request, manifest)
            )
        if args.command == "export":
            authentication.write_signed(args.output, result, key)
            result = {
                "mode": "synthetic_work_suppression_file_saved",
                "checkpoint": authentication.checkpoint(result, key),
                "manifest_hash": result.digest,
                "authentication": _authentication(request),
                "item_count": len(result.body.items),
                "independent_backup_proven": False,
            }
    except (psycopg.Error, ValueError, OSError):
        parser.exit(
            1,
            "Synthetic suppression operation failed; inspect file/metadata/receipt and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
