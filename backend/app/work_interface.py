"""Bounded current-session reads for the synthetic Work screen; no mutation authority."""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import (
    identity,
    work_access,
    work_authority,
    work_context,
    work_lifecycle,
    work_read,
    work_review,
)
from app.config import settings
from app.models import WorkWorkspace

SECTIONS = ("notes", "sources", "parties", "policies", "requests")
MARKER = TypeAdapter(work_lifecycle.Marker)


class Catalogue(work_lifecycle.Contract):
    section: Literal["setup", "notes", "sources", "parties", "policies", "requests"] = "setup"
    after: UUID | None = None
    limit: int = Field(strict=True, ge=1, le=25, default=25)
    request_id: UUID | None = None
    operation: Literal["capture_draft", "correct_note", "forget_note", "confirm_note"] | None = None

    @model_validator(mode="after")
    def bindings(self):
        if self.section == "setup" and self.after is not None:
            raise ValueError("Setup does not accept a cursor")
        if (self.request_id is None) != (self.operation is None):
            raise ValueError("Recovery requires nonce and operation")
        if self.request_id is not None and (self.section != "requests" or self.after is not None):
            raise ValueError("Recovery is a scoped request lookup")
        return self


def get_interface_engines():
    return (
        work_read.get_work_engines()
        if settings.work_notes_interface_enabled and work_context.local_target()
        else None
    )


def _label(value):
    return MARKER.validate_python(value).removeprefix("synthetic:")


def _requests(connection, db, values, body, now):
    params = dict(values, nonce=body.request_id, operation=body.operation, limit=body.limit + 1)
    items = []
    if body.operation != "confirm_note":
        rows = connection.execute(
            text(
                "SELECT id,intent,request_id,target_record_id,expected_revision,state,record_id,result_revision,expires_at,prepared_at FROM work.capture_intents WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) AND (CAST(:nonce AS uuid) IS NULL OR request_id=CAST(:nonce AS uuid)) AND (CAST(:operation AS text) IS NULL OR intent=CAST(:operation AS text)) ORDER BY id LIMIT :limit"
            ),
            params,
        ).all()
        items.extend(
            {
                "id": str(row.id),
                "operation": row.intent,
                "request_id": str(row.request_id),
                "target_record_id": str(row.target_record_id) if row.target_record_id else None,
                "expected_revision": row.expected_revision,
                "state": row.state,
                "record_id": str(row.record_id) if row.record_id else None,
                "revision": (row.result_revision or 1) if row.state == "applied" else None,
                "expires_at": row.expires_at.isoformat(),
                "prepared_at": row.prepared_at.isoformat(),
                "within_lifetime": row.expires_at > now,
            }
            for row in rows
        )
    if body.operation in {None, "confirm_note"}:
        rows = db.execute(
            text(
                "SELECT id,request_id,record_id,reviewed_revision,state,applied_revision,expires_at,created_at FROM public.work_confirmation_requests WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) AND (CAST(:nonce AS uuid) IS NULL OR request_id=CAST(:nonce AS uuid)) ORDER BY id LIMIT :limit"
            ),
            params,
        ).all()
        items.extend(
            {
                "id": str(row.id),
                "operation": "confirm_note",
                "request_id": str(row.request_id),
                "target_record_id": str(row.record_id),
                "expected_revision": row.reviewed_revision,
                "state": row.state,
                "record_id": str(row.record_id) if row.state == "applied" else None,
                "revision": row.applied_revision,
                "expires_at": row.expires_at.isoformat(),
                "prepared_at": row.created_at.isoformat(),
                "within_lifetime": row.expires_at > now,
            }
            for row in rows
        )
    private_count = connection.scalar(
        text(
            "SELECT count(*) FROM work.capture_intents WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND state='pending' AND expires_at>clock_timestamp()"
        ),
        values,
    )
    public_count = db.scalar(
        text(
            "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND state='pending' AND expires_at>clock_timestamp()"
        ),
        values,
    )
    items.sort(key=lambda item: item["id"])
    return items, {"pending_count": private_count + public_count}


def _page(connection, db, authority, workspace, body, section, deadlines):
    values = {
        "workspace": workspace,
        "actor": authority.user.id,
        "session": authority.session.id,
        "after": body.after,
        "limit": body.limit + 1,
    }
    now = connection.scalar(text("SELECT clock_timestamp()"))
    extra = {}
    if section == "requests":
        items, extra = _requests(connection, db, values, body, now)
    elif section == "notes":
        rows = connection.execute(
            text(
                "SELECT m.id,m.revision,m.state,m.retain_until,d.snapshot->>'marker' AS marker FROM work.note_metadata m LEFT JOIN work.drafts d ON d.workspace_id=m.workspace_id AND d.id=m.id AND d.state IN ('draft','confirmed') AND d.retain_until>clock_timestamp() WHERE m.workspace_id=:workspace AND (CAST(:after AS uuid) IS NULL OR m.id>CAST(:after AS uuid)) ORDER BY m.id LIMIT :limit"
            ),
            values,
        ).all()
        items = [
            {
                "id": str(row.id),
                "revision": row.revision,
                "state": row.state,
                "retain_until": row.retain_until.isoformat() if row.retain_until else None,
                "label": _label(row.marker) if row.marker else None,
                "content_available": row.marker is not None,
            }
            for row in rows
        ]
        deadlines.extend(row.retain_until for row in rows[: body.limit] if row.marker is not None)
    elif section == "sources":
        rows = connection.execute(
            text(
                "SELECT s.id,v.marker FROM work.source_registry s JOIN work.validation_records v ON v.workspace_id=s.workspace_id AND v.id=s.id WHERE s.workspace_id=:workspace AND s.is_active AND (CAST(:after AS uuid) IS NULL OR s.id>CAST(:after AS uuid)) ORDER BY s.id LIMIT :limit"
            ),
            values,
        ).all()
        items = [{"id": str(row.id), "label": _label(row.marker)} for row in rows]
    elif section == "parties":
        rows = connection.execute(
            text(
                "SELECT id,marker,retain_until FROM work.parties WHERE workspace_id=:workspace AND state='active' AND retain_until>clock_timestamp() AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit"
            ),
            values,
        ).all()
        items = [{"id": str(row.id), "label": _label(row.marker)} for row in rows]
        deadlines.extend(row.retain_until for row in rows[: body.limit])
    else:
        rows = connection.execute(
            text(
                "SELECT id,max_age_seconds FROM work.retention_policies WHERE workspace_id=:workspace AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit"
            ),
            values,
        ).all()
        items = [{"id": str(row.id), "max_age_seconds": row.max_age_seconds} for row in rows]
    return {
        "items": items[: body.limit],
        "next_cursor": items[body.limit - 1]["id"] if len(items) > body.limit else None,
        **extra,
    }


def _inspect(connection, workspace, record, actor, deadlines):
    row = connection.execute(
        text(
            "SELECT snapshot,encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') AS payload_hash FROM work.drafts WHERE workspace_id=:workspace AND id=:record AND state IN ('draft','confirmed') AND retain_until>clock_timestamp() FOR SHARE"
        ),
        {"workspace": workspace, "record": record},
    ).one_or_none()
    if row is None:
        raise work_review.Rejected(404)
    item = work_lifecycle.Record.model_validate(row.snapshot)
    if item.workspace_id != workspace or item.id != record:
        raise work_read.BrokerUnavailable("Synthetic notes unavailable")
    deadlines.append(item.retain_until)
    sources = connection.execute(
        text(
            "SELECT v.id,v.marker FROM work.validation_records v JOIN work.source_registry s ON s.workspace_id=v.workspace_id AND s.id=v.id WHERE v.workspace_id=:workspace AND s.is_active AND v.id=ANY(:ids) ORDER BY v.id"
        ),
        {"workspace": workspace, "ids": list(item.source_ids)},
    ).all()
    if {value.id for value in sources} != set(item.source_ids):
        raise work_review.Rejected(404)
    policy = connection.scalar(
        text(
            "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=:workspace AND id=:policy"
        ),
        {"workspace": workspace, "policy": item.policy_id},
    )
    if policy is None:
        raise work_read.BrokerUnavailable("Synthetic notes unavailable")
    owner = None
    if item.owner_id is not None:
        party = connection.execute(
            text(
                "SELECT marker,retain_until FROM work.parties WHERE workspace_id=:workspace AND id=:owner AND state='active' AND retain_until>clock_timestamp()"
            ),
            {"workspace": workspace, "owner": item.owner_id},
        ).one_or_none()
        owner = {
            "id": str(item.owner_id),
            "label": _label(party.marker) if party else None,
            "available": party is not None,
        }
        if party:
            deadlines.append(party.retain_until)
    connection.execute(
        text(
            "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(:workspace,:record,:revision,:actor,'draft.read_prepared')"
        ),
        {"workspace": workspace, "record": record, "revision": item.revision, "actor": actor},
    )
    return {
        "item": item.model_dump(mode="json"),
        "payload_hash": row.payload_hash,
        "references": {
            "sources": [{"id": str(value.id), "label": _label(value.marker)} for value in sources],
            "owner": owner,
            "policy": {"id": str(item.policy_id), "max_age_seconds": policy},
        },
    }


class Export(work_lifecycle.Contract):
    selections: list[work_context.Selection] = Field(min_length=1, max_length=10)
    include_drafts: bool = Field(strict=True, default=False)
    purpose: Literal["preview", "download"]
    acknowledge_copy_limits: bool = Field(strict=True, default=False)
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def reviewed(self):
        if len({item.id for item in self.selections}) != len(self.selections):
            raise ValueError("Duplicate selection")
        if self.purpose == "download":
            if not self.acknowledge_copy_limits or self.reviewed_hash is None:
                raise ValueError("Reviewed payload and copy acknowledgement required")
        elif self.reviewed_hash is not None or self.acknowledge_copy_limits:
            raise ValueError("Preview cannot carry a download decision")
        return self


def get_export_engines():
    return get_interface_engines() if settings.work_notes_export_enabled else None


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _export(connection, workspace, body, actor, deadlines):
    records, content_deadlines = {}, []
    for selection in sorted(body.selections, key=lambda item: item.id):
        result = _inspect(connection, workspace, selection.id, actor, content_deadlines)
        note = result["item"]
        if note["revision"] != selection.expected_revision:
            raise work_review.Rejected(409)
        if not note["source_ids"] or (note["state"] != "confirmed" and not body.include_drafts):
            raise work_review.Rejected(404)
        records[selection.id] = {"item": note, "references": result["references"]}
    deadlines.extend(content_deadlines)
    contents = {
        "workspace_id": str(workspace),
        "drafts_permitted": body.include_drafts,
        "retain_until": min(content_deadlines).isoformat(),
        "items": [records[selection.id] for selection in body.selections],
    }
    digest = hashlib.sha256(_canonical(contents)).hexdigest()
    if body.purpose == "download" and not hmac.compare_digest(body.reviewed_hash, digest):
        raise work_review.Rejected(409)
    bundle = {
        "schema_version": 1,
        "mode": "synthetic_work_notes_archive",
        "export_id": str(uuid4()),
        "generated_at": connection.scalar(text("SELECT clock_timestamp()")).isoformat(),
        "current_revisions_only": True,
        "managed_copy": False,
        "execution_allowed": False,
        "raw_transcripts_included": False,
        **contents,
    }
    size = len(_canonical(bundle))
    if size > 32768:
        raise work_review.Rejected(413)
    return {
        "bundle": bundle,
        "bundle_bytes": size,
        "reviewed_hash": digest,
        "purpose": body.purpose,
    }


def read(db, token, csrf, workspace, engines, body=None, record=None, export_body=None):
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.interface_csrf_denied", user=user)
    if (
        db.scalar(
            work_access.assigned(user).where(
                WorkWorkspace.id == workspace, WorkWorkspace.slug.like("synthetic-%")
            )
        )
        is None
    ):
        return identity.denied(db, 404, "work.interface_denied", user=user)
    try:
        if engines is None or not work_context.local_target():
            raise work_read.BrokerUnavailable("Synthetic notes unavailable")
        deadlines = [identity.aware(authority.session.expires_at)]
        with engines.lease(workspace) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic notes unavailable")
            work_read.same_target(db, engine)
            oid = db.scalar(text("SELECT oid FROM pg_database WHERE datname=current_database()"))
            with engine.connect() as connection, connection.begin():
                connection.execute(text("SET LOCAL lock_timeout='2s'"))
                connection.execute(text("SET LOCAL statement_timeout='5s'"))
                try:
                    work_read.restricted_identity(connection, oid, workspace)
                except work_read.BrokerUnavailable:
                    connection.invalidate()
                    raise
                work_review._clock(authority)
                if export_body is not None:
                    result = _export(connection, workspace, export_body, user.id, deadlines)
                elif record is not None:
                    result = _inspect(connection, workspace, record, user.id, deadlines)
                else:
                    sections = SECTIONS if body.section == "setup" else (body.section,)
                    result = {
                        "pages": {
                            section: _page(
                                connection, db, authority, workspace, body, section, deadlines
                            )
                            for section in sections
                        }
                    }
                if min(deadlines) <= connection.scalar(text("SELECT clock_timestamp()")):
                    raise work_review.Rejected(404)
                work_review._clock(authority)
        checked = work_review._clock(authority)
        if min(deadlines) <= checked:
            raise work_review.Rejected(404)
        expiry = min(checked + timedelta(seconds=60), *deadlines)
        authority.session.last_seen_at = checked
        identity.audit(
            db,
            f"work.notes_export_{export_body.purpose}_prepared"
            if export_body
            else "work.notes_inspected"
            if record
            else "work.notes_catalogue",
            "success",
            user=user,
            entity=str(workspace),
            entity_type="work_access_registry",
            metadata={
                "export_id": result["bundle"]["export_id"],
                "records": [
                    {"id": str(item.id), "revision": item.expected_revision}
                    for item in export_body.selections
                ],
                "bundle_bytes": result["bundle_bytes"],
                "retain_until": result["bundle"]["retain_until"],
                "drafts_permitted": export_body.include_drafts,
                "session_id": str(authority.session.id),
            }
            if export_body
            else {"record_id": str(record)}
            if record
            else {"section": body.section},
        )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "mode": "synthetic_notes_export"
                if export_body
                else "synthetic_note_inspection"
                if record
                else "synthetic_notes_catalogue",
                "workspace_id": str(workspace),
                "checked_at": checked.isoformat(),
                "valid_until": expiry.isoformat(),
                "features": {
                    "capture": settings.work_synthetic_capture_enabled,
                    "review": settings.work_draft_review_enabled,
                    "confirmation": settings.work_draft_confirmation_enabled,
                    "changes": settings.work_note_changes_enabled,
                    "export": settings.work_notes_export_enabled,
                },
                "model_invoked": False,
                "execution_allowed": False,
                "real_ingestion_allowed": False,
                **result,
            },
        )
    except work_review.Rejected as error:
        return identity.denied(db, error.status, "work.interface_denied", user=user)
    except (SQLAlchemyError, work_read.BrokerUnavailable, ValidationError):
        identity.audit(
            db,
            "work.interface_unavailable",
            "denied",
            user=user,
            entity=str(workspace),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Synthetic notes unavailable"})
