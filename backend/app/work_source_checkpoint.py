"""Authenticated source checkpoint export, offline verification and reviewed recovery."""

import argparse
import hashlib
import hmac
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import work_drafts, work_lifecycle
from app import work_source_checkpoint_file as files
from app import work_source_withdrawal as withdrawal
from app.config import settings
from app.work_credentials import validate_target
from app.work_suppression_auth import fingerprint, load_key
from app.work_suppression_file import canonical


class Request(work_lifecycle.Contract):
    database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    workspace_id: UUID
    source_ids: tuple[UUID, ...] = Field(default=(), max_length=10)
    auth_key_id: UUID
    auth_key_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision: Literal["export", "preview", "reapply_source_withdrawals"] = "preview"

    @model_validator(mode="after")
    def valid(self):
        if self.source_ids != tuple(sorted(set(self.source_ids))):
            raise ValueError("Select sorted unique source UUIDs")
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "export":
            if (
                not self.source_ids
                or self.expected_manifest_hash is not None
                or self.issued_at is not None
                or self.reviewed_hash is not None
            ):
                raise ValueError("Explicit source export cannot carry target authority")
        elif self.source_ids or self.expected_manifest_hash is None:
            raise ValueError("Recovery requires a pinned file selection only")
        if self.decision == "reapply_source_withdrawals" and (
            self.issued_at is None or self.reviewed_hash is None
        ):
            raise ValueError("Exact current reviewed recovery required")
        if self.decision != "reapply_source_withdrawals" and self.reviewed_hash is not None:
            raise ValueError("Preview/export cannot carry apply authority")
        return self


def _auth(request):
    return {
        "mode": "hmac_sha256",
        "key_id": str(request.auth_key_id),
        "key_fingerprint": request.auth_key_fingerprint,
    }


def _manual(request, sources, **changes):
    return withdrawal.Request(
        database=request.database,
        operator_id=request.operator_id,
        workspace_id=request.workspace_id,
        source_ids=tuple(sources),
        issued_at=request.issued_at,
        **changes,
    )


def _audit(db, request, event, metadata, receipt=None):
    receipt = receipt or uuid4()
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_source_checkpoint','technical_admin',%s,'work_access_registry',%s,'success','{}',%s)",
        (receipt, settings.env, event, str(request.workspace_id), Jsonb(metadata)),
    )
    return receipt


def prepare(db, request: Request):
    """Caller commits export preparation; persistence/trusted retention are separate."""
    if not isinstance(request, Request) or request.decision != "export":
        raise ValueError("Typed explicit source export required")
    plan = withdrawal.reconcile(db, _manual(request, request.source_ids))
    if any(item["is_active"] for item in plan["sources"]) or plan["notes"] or plan["linked"]:
        raise ValueError("Clean withdrawn source set required before export")
    entries = []
    for source in request.source_ids:
        row = db.execute(
            "SELECT a.id,a.occurred_at FROM public.audit_events a WHERE a.environment=%s AND a.event_type='admin.work_sources_withdrawn' AND a.result_status='success' AND a.entity_type='work_access_registry' AND a.entity_id=%s AND a.metadata_json::jsonb->>'workspace_id'=%s AND a.metadata_json::jsonb->>'mode'='synthetic_sources_withdrawn' AND EXISTS(SELECT 1 FROM jsonb_array_elements(a.metadata_json::jsonb->'sources') e WHERE e->>'id'=%s) ORDER BY a.occurred_at DESC,a.id DESC LIMIT 1",
            (settings.env, str(request.workspace_id), str(request.workspace_id), str(source)),
        ).fetchone()
        if row is None:
            raise ValueError("Committed source withdrawal receipt required for every source")
        entries.append(files.Entry(source_id=source, receipt_id=row[0], withdrawn_at=row[1]))
    body = files.Body(
        export_id=uuid4(),
        workspace_id=request.workspace_id,
        exported_by=request.operator_id,
        source_database_oid=plan["database_oid"],
        generated_at=work_drafts._now(db),
        items=tuple(entries),
    )
    manifest = files.Manifest(body=body, digest=files.digest(body))
    _audit(
        db,
        request,
        "admin.work_source_checkpoint_prepared",
        {
            "export_id": str(body.export_id),
            "manifest_hash": manifest.digest,
            "source_ids": [str(value) for value in request.source_ids],
            "item_count": len(entries),
            "authentication": _auth(request),
            "file_saved_verified": False,
            "independent_retention_verified": False,
            "recovery_complete": False,
        },
    )
    return manifest


def _plan(db, request, manifest):
    if (
        not isinstance(request, Request)
        or not isinstance(manifest, files.Manifest)
        or request.decision == "export"
    ):
        raise ValueError("Typed target request/source checkpoint required")
    context = files.require_checkpoint(manifest, request.expected_manifest_hash)
    if manifest.body.workspace_id != request.workspace_id:
        raise ValueError("Source checkpoint workspace mismatch")
    inner = withdrawal.reconcile(
        db, _manual(request, [item.source_id for item in manifest.body.items])
    )
    if work_lifecycle.clock(manifest.body.generated_at) > work_drafts._now(db):
        raise ValueError("Future source checkpoint cannot authorize recovery")
    body = {
        "schema_version": 1,
        "mode": "synthetic_source_checkpoint_recovery_plan",
        "checkpoint": context,
        "authentication": _auth(request),
        "export_id": str(manifest.body.export_id),
        "source_database_oid": manifest.body.source_database_oid,
        "generated_at": manifest.body.generated_at.isoformat(),
        "supplied_decisions": [item.model_dump(mode="json") for item in manifest.body.items],
        "withdrawal": {key: value for key, value in inner.items() if key != "reviewed_hash"},
        "activation_authorized": False,
        "latest_completeness_verified": False,
        "recovery_complete": False,
    }
    plan = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.source-checkpoint-recovery-plan.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(plan)) > 32768:
        raise ValueError("Metadata recovery plan exceeds byte limit")
    return plan, inner


def reconcile(db, request: Request, manifest: files.Manifest):
    """CLI supplies already verified HMAC refs; caller commits both receipts/effects."""
    plan, inner = _plan(db, request, manifest)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(plan["reviewed_hash"], request.reviewed_hash):
        raise ValueError("File-bound plan changed or already applied; preview again")
    result = withdrawal.reconcile(
        db,
        _manual(
            request,
            [item.source_id for item in manifest.body.items],
            reviewed_hash=inner["reviewed_hash"],
            decision="withdraw_sources",
        ),
    )
    receipt = uuid4()
    result = {
        **result,
        "mode": "synthetic_source_checkpoint_reconciled",
        "reconciliation_receipt_id": str(receipt),
        "source_withdrawal_receipt_id": result["receipt_id"],
        "source_checkpoint": plan["checkpoint"],
        "authentication": plan["authentication"],
        "export_id": plan["export_id"],
        "manifest_generated_at": plan["generated_at"],
        "source_decision_receipts": plan["supplied_decisions"],
        "file_bound_plan_hash": plan["reviewed_hash"],
        "latest_completeness_verified": False,
    }
    _audit(db, request, "admin.work_source_checkpoint_reconciled", result, receipt)
    withdrawal._fresh(db, datetime.fromisoformat(inner["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "preview", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True, type=UUID)
        command.add_argument("--recovery-key", required=True)
        command.add_argument("--expected-key-fingerprint", required=True)
        command.add_argument("--environment", required=True, choices=["development", "test"])
        command.add_argument("--database", required=True)
        command.add_argument("--operator", required=True, type=UUID)
        if name == "export":
            command.add_argument("--source", required=True, action="append", type=UUID)
            command.add_argument("--output", required=True)
        else:
            command.add_argument("--manifest", required=True)
            command.add_argument("--expected-manifest-hash", required=True)
        if name == "apply":
            command.add_argument("--issued-at", required=True, type=datetime.fromisoformat)
            command.add_argument("--reviewed-hash", required=True)
            command.add_argument(
                "--decision", required=True, choices=["reapply_source_withdrawals"]
            )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        # Complete protected-file/purpose/HMAC/checkpoint verification precedes connection.
        key = load_key(args.recovery_key, args.expected_key_fingerprint, args.workspace)
        if args.command != "export":
            manifest = files.read_signed(args.manifest, key, args.workspace)
            files.require_checkpoint(manifest, args.expected_manifest_hash)
        request = Request(
            database=args.database,
            workspace_id=args.workspace,
            operator_id=args.operator,
            source_ids=tuple(args.source) if args.command == "export" else (),
            auth_key_id=key.key_id,
            auth_key_fingerprint=fingerprint(key),
            expected_manifest_hash=None
            if args.command == "export"
            else args.expected_manifest_hash,
            issued_at=args.issued_at if args.command == "apply" else None,
            reviewed_hash=args.reviewed_hash if args.command == "apply" else None,
            decision="export"
            if args.command == "export"
            else "reapply_source_withdrawals"
            if args.command == "apply"
            else "preview",
        )
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            if args.command == "export":
                manifest = prepare(db, request)
            else:
                result = reconcile(db, request, manifest)
        if args.command == "export":
            files.write_signed(args.output, manifest, key)
            result = {
                "mode": "synthetic_source_checkpoint_saved",
                "checkpoint": files.checkpoint(manifest, key),
                "independent_retention_verified": False,
                "recovery_complete": False,
            }
    except (psycopg.Error, ValueError, OSError):
        parser.exit(
            1,
            "Source checkpoint operation failed; inspect protected evidence, source receipts and isolated target before deliberate retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
