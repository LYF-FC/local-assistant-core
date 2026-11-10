"""CI-only synthetic browser fixtures, run through the privileged migration container."""

import sys
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal
from app.manage import provision, set_active, set_scope
from app.models import User, MemoryRecord
from app import identity, memory
from app.work_manage import administer

if settings.env != "test" or settings.postgres_db != "butler_test_container":
    raise RuntimeError("Browser fixtures require the disposable container-test database")
action = sys.argv[1] if len(sys.argv) == 2 else ""
with SessionLocal.begin() as db:
    if action == "seed":
        if not db.scalar(text("SELECT pg_get_userbyid(relowner)=current_user FROM pg_class WHERE oid='public.users'::regclass")):
            raise RuntimeError("Browser provisioning requires the actual table owner")
        provision(db, "browser-installation-admin", "Synthetic setup administrator", "synthetic-browser-password-only-0123456789", {"technical_admin", "household_shared"})
        for slug, scopes in (("browser-finance-owner", {"finance_private"}), ("browser-finance-peer", {"finance_private"}), ("browser-finance-admin", {"technical_admin"})):
            provision(db, slug, "Synthetic financial API user", "synthetic-browser-password-only-0123456789", scopes)
        for slug in ("browser-flow", "browser-policy", "browser-revoked"):
            provision(db, slug, "Synthetic browser user", "synthetic-browser-password-only-0123456789", {"household_shared"})
        memory_users = {}
        for slug, scopes in (
            ("browser-memory-owner", {"household_shared", "member_a_private"}),
            ("browser-capture-flow", {"household_shared", "member_a_private"}),
            ("browser-invoices-flow", {"household_shared", "member_a_private"}),
            ("browser-email-flow", {"household_shared", "member_a_private"}),
            ("browser-routines-flow", {"household_shared", "member_a_private"}),
            ("browser-calendar-flow", {"household_shared", "member_a_private"}),
            ("browser-documents-owner", {"household_shared", "member_a_private"}),
            ("browser-documents-viewer", {"household_shared", "member_a_private"}),
            ("browser-tasks-flow", {"household_shared", "member_a_private"}),
            ("browser-reminders-flow", {"household_shared", "member_a_private"}),
            ("browser-reminders-viewer", {"household_shared", "member_a_private"}),
            ("browser-memory-viewer", {"household_shared", "member_a_private"}),
            ("browser-memory-conflict", {"household_shared"}),
            ("browser-memory-race", {"member_a_private"}),
            ("browser-memory-denial", {"member_a_private"}),
            ("browser-discovery-flow", {"member_a_private"}),
            ("browser-discovery-review", {"member_a_private", "member_b_private"}),
            ("browser-discovery-conflict", {"member_a_private"}),
            ("browser-discovery-race", {"member_a_private"}),
            ("browser-context-owner", {"member_a_private", "household_shared"}),
            ("browser-context-conflict", {"member_a_private"}),
            ("browser-context-race", {"member_a_private"}),
            ("browser-context-scope", {"member_a_private", "household_shared"}),
        ):
            memory_users[slug] = provision(db, slug, "Synthetic memory user", "synthetic-browser-password-only-0123456789", scopes)
        for slug in ("browser-work-owner", "browser-work-race", "browser-work-viewer", "browser-work-notes", "browser-work-debrief", "browser-work-export", "browser-work-meeting"):
            provision(db, slug, "Synthetic work user", "synthetic-browser-password-only-0123456789", {"member_a_private", "technical_admin"})
        for slug, user in (("synthetic-browser-work", "browser-work-owner"), ("synthetic-browser-race", "browser-work-race")):
            administer(db, "create-workspace", slug)
            administer(db, "grant", slug, user)
        def entry(identifier, owner, title, scope, content, expired=False):
            now = identity.now_utc()
            record = MemoryRecord(id=UUID(identifier), owner_id=owner.id, scope_key=scope,
                kind="context" if expired else "preference", state="active", revision=1,
                title=title, content=content, source_type="manual", source_reference="Synthetic browser source",
                assessment="confirmed", expires_at=now-timedelta(minutes=1) if expired else None,
                created_at=now-timedelta(minutes=5), updated_at=now-timedelta(minutes=5))
            db.add(record); db.flush(); memory.snapshot(db, owner, record); memory.audit(db, owner, record, "created")
        entry("81111111-1111-4111-8111-111111111111", memory_users["browser-memory-owner"], "Private synthetic marker", "member_a_private", {"text":"Owner-only synthetic data"})
        entry("82222222-2222-4222-8222-222222222222", memory_users["browser-memory-owner"], "Shared synthetic marker", "household_shared", {"text":"Shared synthetic data"})
        entry("83333333-3333-4333-8333-333333333333", memory_users["browser-memory-conflict"], "Structured synthetic memory", "household_shared", {"camera":"synthetic-camera", "tags":["one","two"]})
        entry("84444444-4444-4444-8444-444444444444", memory_users["browser-memory-race"], "Race synthetic marker", "member_a_private", {"text":"Race synthetic data"})
        entry("86666666-6666-4666-8666-666666666666", memory_users["browser-memory-denial"], "Denial synthetic marker", "member_a_private", {"text":"Denial synthetic data"})
        entry("85555555-5555-4555-8555-555555555555", memory_users["browser-memory-owner"], "Expired synthetic context", "member_a_private", {"text":"Expired synthetic data"}, expired=True)
    elif action in {"revoke", "disable"}:
        user = db.scalar(select(User).where(User.slug == "browser-revoked"))
        if user is None:
            raise RuntimeError("Synthetic fixture missing")
        if action == "revoke":
            set_scope(db, user, "household_shared", False)
        else:
            set_active(db, user, False)
    else:
        raise RuntimeError("Unsupported synthetic fixture action")
print("Synthetic browser fixture operation completed")
