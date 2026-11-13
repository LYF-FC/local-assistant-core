"""Disposable synthetic fixtures for the attention inbox browser test (spec 071).

``seed`` runs once through the privileged migration container after ``browser-fixtures.py seed``;
``check`` runs after the browser test and proves the inbox changed nothing. Synthetic
text only. Rows are inserted directly because no real worker or provider may run: this seeds failed
and unknown records and pending approvals that the inbox must read, never create or change.
"""

import hashlib
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, func, select

from app import identity
from app.config import settings
from app.db import SessionLocal
from app.models import (
    Approval,
    AuditEvent,
    AuthRateWindow,
    DocumentRecord,
    FilingExecution,
    InvoiceReview,
    ManualTask,
    NotificationDelivery,
    TaskReminder,
    User,
)

assert (
    settings.env == "test"
    and settings.postgres_db == "butler_test_container"
    and settings.postgres_user in {"postgres", "butler"}
)
SCOPE = "member_b_private"  # isolated: no other browser spec creates records or approvals here


def uid(name):
    return uuid5(NAMESPACE_URL, f"butler-synthetic-inbox-browser-{name}")


phase = sys.argv[1] if len(sys.argv) == 2 else "seed"
assert phase in {"seed", "check", "fresh-login-budget"}
with SessionLocal.begin() as db:
    owner = db.scalar(select(User).where(User.slug == "browser-inbox-flow"))
    assert owner, "browser-fixtures.py seed must run first"
    if phase == "fresh-login-budget":
        # The default browser run uses the whole per-source login window (30 attempts per 15 minutes).
        # Like the other fresh-account phases, give this phase its own budget in the disposable test
        # database. The application limiter is unchanged and still enforced during the run.
        deleted = db.execute(delete(AuthRateWindow)).rowcount
        print(f"Cleared {deleted} disposable login-window rows for the inbox browser phase")
        raise SystemExit(0)
    if phase == "check":
        rows = list(
            db.scalars(
                select(Approval).where(
                    Approval.scope_key == SCOPE,
                    Approval.id.in_([uid(f"approval-{i:02d}") for i in range(26)]),
                )
            )
        )
        assert len(rows) == 26, "approval fixtures are missing"
        assert all(
            r.status == "pending"
            and r.approved_by is None
            and r.consumed_at is None
            and r.resolved_at is None
            for r in rows
        ), "an approval was changed"
        assert (
            db.scalar(select(FilingExecution).where(FilingExecution.id == uid("filing"))).state
            == "failed"
        )
        assert (
            db.scalar(
                select(NotificationDelivery).where(NotificationDelivery.id == uid("notification"))
            ).state
            == "unknown"
        )
        assert (
            db.scalar(select(TaskReminder).where(TaskReminder.id == uid("reminder"))).state
            == "delivered"
        )
        assert (
            db.scalar(select(DocumentRecord).where(DocumentRecord.id == uid("document"))).reviewed
            is False
        )
        queries = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == "approval.query",
                    AuditEvent.initiator_id == str(owner.id),
                )
            )
        )
        assert queries, "the real browser run wrote no approval.query audit event"
        assert all(
            e.entity_id is None
            and e.approval_id is None
            and e.before_json is None
            and e.after_json is None
            for e in queries
        )
        assert all(set(e.metadata_json) == {"returned"} for e in queries), (
            "approval.query metadata is not count-only"
        )
        forbidden = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.initiator_id == str(owner.id),
                AuditEvent.event_type.like("approval.%"),
                AuditEvent.event_type != "approval.query",
            )
        )
        assert forbidden == 0, "the inbox user recorded an approval event other than approval.query"
        print(
            f"Inbox browser run verified: 26 approvals untouched, {len(queries)} approval.query events, no other approval events"
        )
        raise SystemExit(0)
    now = identity.now_utc()
    past = now - timedelta(hours=2)

    def task(name, title, **extra):
        row = ManualTask(
            id=uid(name),
            owner_id=owner.id,
            scope_key=SCOPE,
            state="active",
            status="open",
            revision=1,
            title=title,
            details="Synthetic inbox fixture",
            source_reference="Synthetic inbox fixture",
            created_at=past,
            updated_at=past,
            **extra,
        )
        db.add(row)
        db.flush()
        return row

    task("overdue", "Synthetic overdue inbox task", due_at=now - timedelta(days=1))
    reminded = task("reminded", "Synthetic inbox delivered reminder")
    # Database triggers require every record to be created in its initial state and then moved
    # through an allowed transition, so the fixture does the same.
    reminder = TaskReminder(
        id=uid("reminder"),
        task_id=reminded.id,
        owner_id=owner.id,
        scope_key=SCOPE,
        revision=1,
        cycle=1,
        policy_revision=0,
        task_revision=1,
        state="scheduled",
        scheduled_at=past + timedelta(minutes=1),
        next_attempt_at=past + timedelta(minutes=1),
        created_at=past,
        updated_at=past,
    )
    db.add(reminder)
    db.flush()
    reminder.revision, reminder.state, reminder.next_attempt_at = 2, "delivered", None
    reminder.delivered_at = reminder.updated_at = past + timedelta(minutes=2)
    db.flush()
    delivery = NotificationDelivery(
        id=uid("notification"),
        reminder_id=reminder.id,
        owner_id=owner.id,
        scope_key=SCOPE,
        cycle=1,
        channel="synthetic",
        recipient_ref="synthetic-recipient",
        revision=1,
        state="pending",
        attempts=0,
        next_attempt_at=past,
        created_at=past,
        updated_at=past,
    )
    db.add(delivery)
    db.flush()
    delivery.revision, delivery.state, delivery.attempts = 2, "unknown", 1
    delivery.next_attempt_at, delivery.reason = now + timedelta(hours=1), "ambiguous_outcome"
    db.flush()

    def make_document(name, title, reviewed):
        text = f"Synthetic inbox document text {name}"
        row = DocumentRecord(
            id=uid(name),
            owner_id=owner.id,
            scope_key=SCOPE,
            state="active",
            revision=1,
            title=title,
            filename=f"synthetic-inbox-{name}.txt",
            source_reference="Synthetic inbox fixture",
            content_text=text,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            byte_size=len(text.encode()),
            reviewed=False,
            created_at=past,
            updated_at=past,
        )
        db.add(row)
        db.flush()
        if reviewed:  # documents are created unreviewed; review is a later revision
            row.reviewed, row.revision, row.updated_at = True, 2, past + timedelta(minutes=1)
            db.flush()
        return row

    make_document("document", "Synthetic inbox unreviewed document", False)
    # A filing request can only exist for a reviewed document with an approved current plan, so the
    # failed request belongs to a separate, already reviewed document (not in "needing review").
    document = make_document("filed-document", "Synthetic inbox filed document", True)
    plan_path = "synthetic/inbox-invoice.pdf"
    review = InvoiceReview(
        document_id=document.id,
        owner_id=owner.id,
        scope_key=SCOPE,
        state="draft",
        revision=1,
        source_revision=2,
        data={"source": {"revision": 2, "sha256": document.sha256}},
        created_at=past,
        updated_at=past,
    )
    db.add(review)
    db.flush()
    review.state, review.revision, review.updated_at = "reviewed", 2, past + timedelta(minutes=1)
    review.issuer_key, review.number_key = "synthetic-inbox-issuer", "synthetic-inbox-1"
    review.data = {
        "source": {"revision": 2, "sha256": document.sha256},
        "decisions": {},
        "filing_plan": {"state": "approved", "relative_path": plan_path, "approved_revision": 2},
    }
    db.flush()
    filing = FilingExecution(
        id=uid("filing"),
        document_id=document.id,
        owner_id=owner.id,
        scope_key=SCOPE,
        plan_revision=2,
        source_revision=2,
        destination_key=hashlib.sha256(f"{SCOPE}:{plan_path}".encode()).hexdigest(),
        destination="synthetic",
        revision=1,
        state="pending",
        attempts=0,
        next_attempt_at=past,
        created_at=past,
        updated_at=past,
    )
    db.add(filing)
    db.flush()
    # Follow the sealed transitions: claim (consumes the authorization), then fail the attempt.
    claimed = past + timedelta(minutes=3)
    filing.revision, filing.attempts, filing.attempt_started_at = 2, 1, claimed
    filing.authorization_consumed_at = filing.updated_at = claimed
    db.flush()
    filing.revision, filing.state, filing.attempt_started_at, filing.next_attempt_at = (
        3,
        "failed",
        None,
        None,
    )
    filing.resolved_at, filing.reason, filing.updated_at = claimed, "attempts_exhausted", claimed
    db.flush()
    # 26 bound, unexpired approvals so one page and a next page exist. One is requested by another
    # member. The sealed payload carries a marker that must never reach the browser.
    for index in range(26):
        db.add(
            Approval(
                id=uid(f"approval-{index:02d}"),
                scope_key=SCOPE,
                action_type="validation.noop",
                status="pending",
                requested_by=str(owner.id) if index else "synthetic-other-member",
                request_payload={"marker": "SYNTHETIC-APPROVAL-PAYLOAD-MARKER"},
                payload_hash=hashlib.sha256(f"payload-{index}".encode()).hexdigest(),
                policy_version="synthetic-policy-1",
                expires_at=now + timedelta(hours=1),
                requested_at=past,
            )
        )
print("Synthetic inbox browser fixture seeded")
