"""CI-only confirmed agenda/follow-up references for actual HTTPS browser acceptance."""

import os
from datetime import UTC, datetime, timedelta

import psycopg
from sqlalchemy import select

from app import work_drafts, work_lifecycle, work_parties
from app.config import settings
from app.db import SessionLocal
from app.models import User, WorkWorkspace

assert settings.env == "test" and settings.postgres_db == "butler_test_container"
assert os.geteuid() == 10001
with SessionLocal() as identity:
    workspace = identity.scalar(select(WorkWorkspace.id).where(WorkWorkspace.slug == "synthetic-adapter-ci"))
    actor = identity.scalar(select(User.id).where(User.slug == "browser-work-meeting"))
assert workspace is not None and actor is not None
with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db, db.transaction():
    source = db.execute("SELECT id FROM work.source_registry WHERE workspace_id=%s AND is_active ORDER BY id LIMIT 1", (workspace,)).fetchone()[0]
    policy = db.execute("SELECT id FROM work.retention_policies WHERE workspace_id=%s ORDER BY id LIMIT 1", (workspace,)).fetchone()[0]
    now = datetime.now(UTC)
    until = now + timedelta(hours=1)
    owner = work_parties.create(db, workspace, policy, "synthetic:meeting-owner", until)
    for kind, marker, selected_owner, due in (
        ("action", "meeting-action-owned", owner.id, now + timedelta(minutes=10)),
        ("action", "meeting-action-unknown", None, None),
        ("decision", "meeting-decision", None, None),
        ("question", "meeting-question", None, None),
        ("observation", "meeting-observation", None, None),
    ):
        record = work_drafts.create(db, workspace, actor, policy, work_lifecycle.Draft(kind=kind, marker="synthetic:"+marker, source_ids=(source,), owner_id=selected_owner, due_at=due, retain_until=until))
        work_drafts.transition(db, workspace, actor, record.id, record.revision, "confirm")
print("Synthetic confirmed meeting references prepared; no payloads displayed")
