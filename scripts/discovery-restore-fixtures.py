"""Disposable logical-restore sentinel for explicit v2 ideas and enriched history."""

import secrets
import sys
from datetime import timedelta
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select
from app import discovery, discovery_digest, identity, memory
from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, AuthSession, MemoryRecord, MemoryRevision, User
from app.manage import set_scope

assert settings.env == "test" and settings.postgres_db in {
    "butler_test",
    "butler_test_restore",
}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    for name in ("idea", "enriched"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-discovery-restore-" + name)
        if phase == "seed":
            assert db.get(MemoryRecord, identifier) is None
            content = discovery.IdeaEnvelope(
                record_type="discovery_proposal",
                schema_version=2,
                summary="Synthetic unknown restore idea",
            ).model_dump(mode="json")
            now = identity.now_utc()
            record = MemoryRecord(
                id=identifier,
                owner_id=owner.id,
                scope_key="member_a_private",
                kind="experience",
                state="active",
                revision=1,
                title="Synthetic Discovery restore",
                content=content,
                source_type="manual",
                source_reference="Synthetic restore fixture only",
                assessment="tentative",
                created_at=now,
                updated_at=now,
            )
            db.add(record)
            db.flush()
            memory.snapshot(db, owner, record)
            memory.audit(db, owner, record, "created")
            if name == "enriched":
                record.content = discovery.ProposalEnvelope(
                    record_type="discovery_proposal",
                    schema_version=2,
                    topic="synthetic-restore",
                    summary="Synthetic enriched restore idea",
                    evidence=[
                        discovery.Evidence(
                            title="Synthetic inert source",
                            url="https://example.org/synthetic-restore",
                            observed_at="2026-01-01T00:00:00Z",
                        )
                    ],
                    feedback=discovery.Feedback(
                        choice="later",
                        note="Synthetic retained feedback",
                        recorded_at=now,
                    ),
                ).model_dump(mode="json")
                record.revision = 2
                record.updated_at = identity.now_utc()
                db.flush()
                memory.snapshot(db, owner, record)
                memory.audit(db, owner, record, "corrected")
        else:
            record = db.get(MemoryRecord, identifier)
            envelope = discovery.parse(record)
            assert envelope is not None and envelope.schema_version == 2
            snapshots = list(
                db.scalars(
                    select(MemoryRevision.snapshot)
                    .where(MemoryRevision.memory_id == identifier)
                    .order_by(MemoryRevision.revision)
                )
            )
            if name == "idea":
                assert (
                    envelope.stage == "idea"
                    and envelope.evidence == []
                    and record.assessment == "tentative"
                )
                assert [s["content"]["stage"] for s in snapshots] == ["idea"]
            else:
                assert (
                    envelope.stage == "proposal"
                    and len(envelope.evidence) == 1
                    and envelope.feedback.choice == "later"
                )
                assert [s["content"]["stage"] for s in snapshots] == [
                    "idea",
                    "proposal",
                ]
print(
    "Synthetic Discovery v2 idea/enrichment/evidence/feedback/history restore sentinel verified"
)

# A real prepared receipt is retained as metadata only; the originating authority is retired.
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    if phase == "seed":
        set_scope(db, owner, "member_a_private", True)
        token, csrf, now = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            identity.now_utc(),
        )
        session = AuthSession(
            user_id=owner.id,
            token_hash=identity.digest(token),
            csrf_hash=identity.digest(csrf),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(session)
        db.flush()
        selections = [
            {
                "id": str(
                    uuid5(NAMESPACE_URL, "butler-synthetic-discovery-restore-" + name)
                ),
                "expected_revision": 1 if name == "idea" else 2,
            }
            for name in ("idea", "enriched")
        ]
        result = discovery_digest.prepare(
            db,
            token,
            csrf,
            discovery_digest.Request(
                scope="member_a_private", selections=selections, purpose="preview"
            ),
        )
        assert result.status == 200
        session.revoked_at = identity.now_utc()
        set_scope(db, owner, "member_a_private", False)
    else:
        receipt = db.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "discovery.digest_preview",
                AuditEvent.initiator_id == str(owner.id),
                AuditEvent.scope_key == "member_a_private",
            )
        )
        assert receipt and receipt.metadata_json["selected_count"] == 2
        assert len(receipt.metadata_json["reviewed_hash"]) == 64
        assert set(receipt.metadata_json) == {
            "schema_version",
            "session_id",
            "reviewed_hash",
            "selected_count",
            "valid_until",
            "export_id",
        }
        assert (
            db.get(AuthSession, UUID(receipt.metadata_json["session_id"])).revoked_at
            is not None
        )
print(
    "Synthetic Discovery digest receipt metadata and retired session preserved across restore"
)
