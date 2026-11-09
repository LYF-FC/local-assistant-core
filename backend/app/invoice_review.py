"""Source-bound invoice field review; no mailbox, model, filing or payment effects."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator
from sqlalchemy import or_, select, update

from app import documents, identity, invoice_filing
from app import invoice_fields as fields
from app.manual_tasks import Scoped, authority, stamp
from app.models import DocumentRecord as Source
from app.models import InvoiceReview as Review
from app.models import InvoiceRevision as Revision


class Expected(Scoped):
    expected_document_revision: int = Field(strict=True, ge=1)
    expected_review_revision: int | None = Field(default=None, strict=True, ge=1)


class Confirm(Expected):
    decisions: fields.Decisions
    attest_original: Literal[True]

    @field_validator("attest_original", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit original verification required")
        return value


class Plan(Expected):
    folder: str | None = Field(default=None, max_length=204)
    filename: str | None = Field(default=None, max_length=160)


class ApprovePlan(Expected):
    acknowledge_plan_only: Literal[True]
    acknowledge_duplicate_limits: Literal[True]
    _explicit = field_validator(
        "acknowledge_plan_only", "acknowledge_duplicate_limits", mode="before"
    )(Confirm.explicit.__func__)


class History(Scoped):
    after: int = Field(default=0, strict=True, ge=0)


class Export(History):
    acknowledge_copy_limits: Literal[True]
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(Confirm.explicit.__func__)


class Duplicates(Scoped):
    after: UUID | None = None


def eligible(source):
    return (
        source.state == "active"
        and source.reviewed
        and (source.extraction_json is None or source.extraction_json["status"] == "ready")
    )


def saved(row):
    return {
        "document_id": str(row.document_id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "source_revision": row.source_revision,
        "data": row.data,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }


def receipt(source, row, user):
    status = (
        "missing"
        if row is None
        else "forgotten"
        if row.state == "forgotten"
        else "stale"
        if row.source_revision != source.revision
        else "source_unreviewed"
        if not eligible(source)
        else row.state
    )
    return {
        "schema_version": 1,
        "document_id": str(source.id),
        "scope": source.scope_key,
        "current_document_revision": source.revision,
        "status": status,
        "review_revision": row.revision if row else None,
        "can_edit": source.owner_id == user.id,
        "review": saved(row) if row and status in {"draft", "reviewed"} else None,
    }


def audit(db, user, source, row, operation, **metadata):
    identity.audit(
        db,
        "invoices." + operation,
        "success",
        user=user,
        scope=source.scope_key,
        entity_type="document",
        entity=str(source.id),
        metadata={
            "document_revision": source.revision,
            "review_revision": row.revision if row else None,
            **metadata,
        },
    )


def remember(db, user, row):
    db.flush()
    db.add(
        Revision(
            document_id=row.document_id,
            revision=row.revision,
            actor_id=user.id,
            snapshot=saved(row) if row.state != "forgotten" else None,
            created_at=row.updated_at,
        )
    )


def forget_for_document(db, user, source):
    row = db.scalar(
        select(Review)
        .where(Review.document_id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.state == "forgotten":
        return
    row.state, row.data, row.issuer_key, row.number_key = "forgotten", None, None, None
    row.revision += 1
    row.updated_at = identity.now_utc()
    db.flush()
    db.execute(
        update(Revision).where(Revision.document_id == row.document_id).values(snapshot=None)
    )
    remember(db, user, row)
    audit(db, user, source, row, "forgotten")


def duplicate_page(db, user, source, row, after):
    # Join only current eligible reviews for key matching; original-byte hints need no field attestation.
    has_keys = bool(
        row
        and row.state == "reviewed"
        and row.source_revision == source.revision
        and eligible(source)
        and row.issuer_key
        and row.number_key
    )
    keyed = (
        select(Review.document_id)
        .join(Source, Source.id == Review.document_id)
        .where(
            *documents.visible(user, source.scope_key),
            Source.state == "active",
            Source.reviewed.is_(True),
            Review.state == "reviewed",
            Review.source_revision == Source.revision,
            Review.issuer_key == row.issuer_key,
            Review.number_key == row.number_key,
        )
        if has_keys
        else None
    )
    conditions = [Source.sha256 == source.sha256]
    if keyed is not None:
        conditions.append(Source.id.in_(keyed))
    query = select(Source).where(
        *documents.visible(user, source.scope_key),
        Source.state == "active",
        Source.id != source.id,
        or_(*conditions),
    )
    if after:
        query = query.where(Source.id > after)
    matches = list(
        db.scalars(
            query.order_by(Source.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    # Pin current key candidates after source locks; recheck before releasing any match.
    items = []
    for candidate in matches[:25]:
        reason = "identical_original" if candidate.sha256 == source.sha256 else None
        if reason is None:
            other = db.scalar(
                select(Review)
                .where(Review.document_id == candidate.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            if (
                other
                and eligible(candidate)
                and other.state == "reviewed"
                and other.source_revision == candidate.revision
                and (other.issuer_key, other.number_key) == (row.issuer_key, row.number_key)
            ):
                reason = "same_reviewed_issuer_number"
        if reason:
            items.append(
                {"document": documents.presented(candidate, user, text=False), "reason": reason}
            )
    return {
        "items": items,
        "next_cursor": str(matches[24].id) if len(matches) > 25 else None,
        "notice": "Possible visible duplicates only. No merge, deletion, payment or filing action. Matching keys do not prove business identity.",
    }


def operate(db, token, csrf, identifier, body, operation):
    write = operation in {"prepare", "review", "forget", "plan", "approve_plan", "withdraw_plan"}
    current = authority(db, token, csrf, body.scope, exclusive_user=write, event_prefix="invoices")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    source = db.scalar(
        select(Source)
        .where(Source.id == identifier, *documents.visible(user, body.scope))
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "invoices.session_denied", user=user)
    if source is None:
        return identity.denied(db, 404, "invoices.not_found", user=user)
    if (
        operation
        in {
            "prepare",
            "review",
            "forget",
            "history",
            "export",
            "plan",
            "approve_plan",
            "withdraw_plan",
        }
        and source.owner_id != user.id
    ):
        return identity.denied(db, 403, "invoices.owner_denied", user=user)
    row = db.scalar(
        select(Review)
        .where(Review.document_id == source.id)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if source.state == "forgotten":
        audit(db, user, source, row, "forgotten_read")
        return identity.Result(410, receipt(source, row, user))
    if operation in {"history", "export"}:
        rows = list(
            db.scalars(
                select(Revision)
                .where(Revision.document_id == source.id, Revision.revision > body.after)
                .order_by(Revision.revision)
                .limit(6)
            )
        )
        audit(db, user, source, row, operation, returned=min(len(rows), 5))
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "document_id": str(source.id),
                "scope": body.scope,
                "state": row.state if row else "missing",
                "current_review_revision": row.revision if row else None,
                "managed_copy": False if operation == "export" else None,
                "items": [
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id),
                        "created_at": stamp(r.created_at),
                        "snapshot": r.snapshot,
                    }
                    for r in rows[:5]
                ],
                "next_cursor": rows[4].revision if len(rows) > 5 else None,
            },
        )
    if operation == "duplicates":
        result = duplicate_page(db, user, source, row, body.after)
        if identity.resolve(db, token, refresh_session=True) is None:
            return identity.denied(db, 401, "invoices.session_denied", user=user)
        audit(db, user, source, row, "duplicates", returned=len(result["items"]))
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "document_id": str(source.id),
                "scope": body.scope,
                "current_document_revision": source.revision,
                **result,
            },
        )
    if not write:
        audit(db, user, source, row, "read")
        return identity.Result(200, receipt(source, row, user))
    if source.revision != body.expected_document_revision:
        return identity.denied(db, 409, "invoices.source_changed", user=user)
    if row and row.state == "forgotten":
        audit(db, user, source, row, "forgotten_read")
        return identity.Result(410, receipt(source, row, user))
    if (
        operation == "prepare"
        and row
        and row.state == "draft"
        and row.source_revision == source.revision
        and eligible(source)
        and (body.expected_review_revision is None or body.expected_review_revision <= row.revision)
    ):
        audit(db, user, source, row, "replayed")
        return identity.Result(200, receipt(source, row, user))
    if (row.revision if row else None) != body.expected_review_revision:
        return identity.denied(db, 409, "invoices.review_changed", user=user)
    if operation == "forget":
        if row is None:
            return identity.denied(db, 404, "invoices.not_found", user=user)
        forget_for_document(db, user, source)
        return identity.Result(200, receipt(source, row, user))
    if not eligible(source):
        return identity.denied(db, 409, "invoices.source_review_required", user=user)
    if row and row.revision >= 100:
        return identity.denied(db, 429, "invoices.history_limit", user=user)
    if operation in {"plan", "approve_plan", "withdraw_plan"}:
        if row is None or row.state != "reviewed" or row.source_revision != source.revision:
            return identity.denied(db, 409, "invoices.current_field_review_required", user=user)
        plan = row.data.get("filing_plan")
        if operation == "plan":
            try:
                plan = invoice_filing.propose(source, row, body.folder, body.filename)
            except ValueError:
                return identity.denied(db, 422, "invoices.invalid_filing_plan", user=user)
        elif not plan or plan["state"] not in (
            {"proposed"} if operation == "approve_plan" else {"proposed", "approved"}
        ):
            return identity.denied(db, 409, "invoices.filing_plan_changed", user=user)
        else:
            plan = {
                **plan,
                "state": "approved" if operation == "approve_plan" else "withdrawn",
                "approved_revision": row.revision + 1 if operation == "approve_plan" else None,
            }
        row.data = {**row.data, "filing_plan": plan}
        row.revision += 1
        row.updated_at = identity.now_utc()
        remember(db, user, row)
        audit(db, user, source, row, operation)
        return identity.Result(200, receipt(source, row, user))
    now = identity.now_utc()
    if operation == "prepare":
        if row is None:
            row = Review(
                document_id=source.id,
                owner_id=user.id,
                scope_key=source.scope_key,
                revision=1,
                created_at=now,
            )
            db.add(row)
        else:
            row.revision += 1
        row.state, row.source_revision, row.data, row.issuer_key, row.number_key = (
            "draft",
            source.revision,
            fields.prepare(source),
            None,
            None,
        )
    else:
        if row is None or row.source_revision != source.revision:
            return identity.denied(db, 409, "invoices.prepare_required", user=user)
        try:
            decisions = fields.review(source, body.decisions)
        except ValueError:
            return identity.denied(db, 422, "invoices.invalid_decisions", user=user)
        row.state = "reviewed"
        row.revision += 1
        row.data = {**row.data, "decisions": decisions, "filing_plan": None}
        row.issuer_key, row.number_key = (
            fields.key(decisions["issuer"]["value"]),
            fields.key(decisions["invoice_number"]["value"]),
        )
    row.updated_at = now
    remember(db, user, row)
    audit(db, user, source, row, operation)
    return identity.Result(200, receipt(source, row, user))
