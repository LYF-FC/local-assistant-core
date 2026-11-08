"""Disposable container CI only: protected volume and managed synthetic login."""

import os
from datetime import UTC, datetime, timedelta
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from sqlalchemy import select

from app import work_adapter, work_credentials, work_drafts, work_lifecycle
from app.config import settings
from app.db import SessionLocal
from app.models import User, WorkWorkspace
from app.work_manage import administer
from app.work_storage import provision
from app.work_notes_storage import provision_changes

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
directory = Path("/run/butler-work")
assert os.geteuid() == 10001 and directory.stat().st_uid == 10001
assert directory.stat().st_mode & 0o777 == 0o700
if sys.argv[1] in {"review", "draft-id"}:
    with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
        if sys.argv[1] == "draft-id":
            print(db.execute("SELECT id FROM work.drafts WHERE snapshot->>'marker'='synthetic:tls-review'").fetchone()[0])
            sys.exit(0)
        with SessionLocal() as identity_db:
            workspace = identity_db.scalar(select(WorkWorkspace.id).where(WorkWorkspace.slug == "synthetic-adapter-ci"))
            actor = identity_db.scalar(select(User.id).where(User.slug == "browser-work-owner"))
        source = db.execute("SELECT id FROM work.validation_records WHERE workspace_id=%s", (workspace,)).fetchone()[0]
        policy = uuid4()
        db.execute("INSERT INTO work.retention_policies VALUES(%s,%s,86400)", (workspace,policy))
        db.execute("INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)", (workspace,source))
        provision_changes(db, "synthetic-adapter-ci")
        work_drafts.create(db,workspace,actor,policy,work_lifecycle.Draft(kind="decision",marker="synthetic:tls-review",source_ids=(source,),retain_until=datetime.now(UTC)+timedelta(hours=1)))
        work_drafts.create(db,workspace,actor,policy,work_lifecycle.Draft(kind="question",marker="synthetic:export-draft",source_ids=(source,),retain_until=datetime.now(UTC)+timedelta(hours=1)))
elif sys.argv[1] == "remove":
    (directory / work_adapter.FILE).unlink()
else:
    slug = "synthetic-adapter-ci"
    secret = "synthetic-container-file-secret-only-0123456789"
    with SessionLocal.begin() as db:
        administer(db, "create-workspace", slug)
        administer(db, "grant", slug, "browser-work-owner")
        administer(db, "grant", slug, "browser-work-notes")
        administer(db, "grant", slug, "browser-work-debrief")
        administer(db, "grant", slug, "browser-work-export")
        administer(db, "grant", slug, "browser-work-meeting")
        identifier = db.scalar(select(WorkWorkspace.id).where(WorkWorkspace.slug == slug))
    with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
        provision(db, slug)
    with SessionLocal.begin() as db:
        administer(db, "disable", slug)
    with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
        work_credentials.administer(db, "bootstrap", slug, secret)
    with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
        bundle = work_adapter.prepare(db, slug, secret)
    work_adapter.publish(directory, bundle)
    with SessionLocal.begin() as db:
        administer(db, "enable", slug)
    with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
        db.execute("INSERT INTO work.validation_records (workspace_id,id,marker) VALUES (%s,%s,'synthetic:container-adapter')", (identifier, uuid4()))
print("Synthetic adapter fixture complete; no credentials displayed")
