"""MVP-01 owner rehearsal fixtures, run through the privileged migration container (spec 076).

Synthetic only. Refuses anything but the exact disposable rehearsal database. Reads the synthetic
passwords from the process environment (never from arguments, files or logs) and prints only fixed
non-secret lines. Actions: check | provision | identity.
"""

import os
import sys

from sqlalchemy import func, select, text

from app.config import settings
from app.db import SessionLocal
from app.manage import provision, replace_password
from app.models import CalendarSource, ManualTask, User

DATABASE = "butler_test_mvp01_owner"
OWNER, PEER = "mvp01-owner", "mvp01-peer"
OWNER_SCOPES, PEER_SCOPES = {"household_shared", "member_a_private"}, {"member_b_private"}
if settings.env != "test" or settings.postgres_db != DATABASE:
    raise RuntimeError("The MVP-01 rehearsal fixtures require the exact disposable rehearsal database")
action = sys.argv[1] if len(sys.argv) == 2 else ""
with SessionLocal.begin() as db:
    if not db.scalar(
        text("SELECT pg_get_userbyid(relowner)=current_user FROM pg_class WHERE oid='public.users'::regclass")
    ):
        raise RuntimeError("The rehearsal fixtures require the actual users-table owner")
    if db.scalar(text("SELECT current_database()")) != DATABASE:
        raise RuntimeError("The rehearsal fixtures require the exact disposable rehearsal database")
    owner = db.scalar(select(User).where(User.slug == OWNER))
    peer = db.scalar(select(User).where(User.slug == PEER))
    if action == "check":
        tasks = db.scalar(select(func.count()).select_from(ManualTask).where(ManualTask.title.like("MVP-01 synthetic:%"))) if owner else 0
        sources = db.scalar(select(func.count()).select_from(CalendarSource)) if owner else 0
        print(f"owner={'exists' if owner else 'missing'} peer={'exists' if peer else 'missing'} agenda_tasks={tasks} calendar_sources={sources}")
    elif action == "provision":
        owner_password, peer_password = os.environ.get("BUTLER_MVP01_OWNER_PASSWORD"), os.environ.get("BUTLER_MVP01_PEER_PASSWORD")
        if owner is None:
            if not owner_password:
                raise RuntimeError("A synthetic owner password is required for first provisioning")
            provision(db, OWNER, "Synthetic MVP-01 adult (rehearsal)", owner_password, OWNER_SCOPES)
            print("owner=created")
        else:
            print("owner=kept")
        if peer_password:
            if peer is None:
                provision(db, PEER, "Synthetic MVP-01 peer (rehearsal)", peer_password, PEER_SCOPES)
                print("peer=created")
            else:
                replace_password(db, peer, peer_password)
                print("peer=password-replaced")
    elif action == "identity":
        head = db.scalar(text("SELECT version_num FROM alembic_version"))
        installation = db.execute(text("SELECT revision, created_at FROM installation_config WHERE id=1")).one_or_none()
        print(f"database={settings.postgres_db} alembic_head={head} installation_revision={installation[0] if installation else 'none'} installation_created={installation[1].isoformat() if installation else 'none'} migration_user={settings.postgres_user}")
    else:
        raise RuntimeError("Unknown action")
