"""Synthetic installation identity/configuration proof for the fixed native restore harness."""

import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app import identity, installation
from app.config import settings
from app.db import SessionLocal
from app.manage import set_scope
from app.models import InstallationConfig, InstallationRevision, User

if (
    settings.env != "test"
    or settings.postgres_db not in {"butler_test", "butler_test_restore"}
    or settings.postgres_user != "postgres"
):
    raise RuntimeError("Installation restore proof requires the fixed disposable owner harness")
manifest = Path(os.environ["BUTLER_INSTALLATION_RESTORE_MANIFEST_FILE"])
with SessionLocal.begin() as db:
    row = db.scalar(select(InstallationConfig).where(InstallationConfig.id == 1).with_for_update())
    phase = sys.argv[1]
    if phase == "seed":
        user = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
        set_scope(db, user, "technical_admin", True)
        row.installation_id = row.installation_id or uuid4()
        row.revision += 1
        row.configuration = {
            "schema_version": 1,
            "defaults": {"languages": ["en", "fr"], "timezone": "UTC"},
        }
        row.updated_by = user.id
        row.updated_at = identity.now_utc()
        installation.remember(db, user, row)
        installation.audit(db, user, row, "restore_fixture")
        db.flush()
        payload = {
            "record": installation.saved(row),
            "history": db.query(InstallationRevision).count(),
        }
        with manifest.open("x") as output:
            os.chmod(manifest, 0o600)
            json.dump(payload, output)
    elif phase == "check":
        expected = json.loads(manifest.read_text())
        assert installation.saved(row) == expected["record"]
        assert db.query(InstallationRevision).count() == expected["history"]
        revision = db.scalar(
            select(InstallationRevision).where(InstallationRevision.revision == row.revision)
        )
        assert revision.snapshot == expected["record"]
        assert set(row.configuration) == {"schema_version", "defaults"}
        assert set(row.configuration["defaults"]) == {"languages", "timezone"}
    else:
        raise RuntimeError("Unknown phase")
print("Synthetic installation identity, bounded defaults and history verified")
