import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import settings

pytestmark = pytest.mark.integration


def test_schema_round_trip_and_synthetic_record_survival():
    if os.environ.get("BUTLER_RUN_DB_TESTS") != "1":
        pytest.skip("explicit disposable database opt-in required")
    assert settings.env == "test", "never migrate a non-test environment in this test"
    assert settings.postgres_db.startswith("butler_test"), "use a disposable test database"
    backend = Path(__file__).resolve().parents[2]

    def migrate(*args):
        result = subprocess.run(
            ["alembic", *args], cwd=backend, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr

    migrate("upgrade", "head")
    migrate("check")
    engine = create_engine(settings.database_url)
    try:
        assert {
            "users",
            "scopes",
            "user_scopes",
            "tasks",
            "approvals",
            "audit_events",
            "durable_jobs",
            "job_outbox",
            "memory_records",
            "memory_revisions",
            "work_workspaces",
            "work_access_grants",
            "work_confirmation_requests",
        } <= set(inspect(engine).get_table_names())
        assert {
            "validation_records",
            "validation_audit",
            "read_attempts",
            "retention_policies",
            "source_registry",
            "drafts",
            "draft_revisions",
            "draft_audit",
            "draft_tombstones",
            "draft_reviews",
            "draft_confirmations",
            "parties",
            "party_audit",
            "capture_intents",
            "capture_audit",
        } <= set(inspect(engine).get_table_names(schema="work"))
        assert "note_metadata" in inspect(engine).get_view_names(schema="work")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='work' AND c.relname IN ('validation_records','validation_audit','read_attempts','retention_policies','source_registry','drafts','draft_revisions','draft_audit','draft_tombstones','draft_reviews','draft_confirmations','parties','party_audit','capture_intents','capture_audit') AND c.relrowsecurity AND c.relforcerowsecurity"
                    )
                ).scalar_one()
                == 15
            )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE tgname='work_registry_barrier' AND tgenabled='O' AND NOT tgisinternal"
                    )
                ).scalar_one()
                == 2
            )
        synthetic_user_id, synthetic_workspace_id = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as connection:
            scopes = connection.execute(text("SELECT key FROM scopes")).scalars().all()
            assert set(scopes) == {
                "household_shared",
                "member_a_private",
                "member_b_private",
                "parents_child",
                "member_business",
                "finance_private",
                "technical_admin",
            }
            connection.execute(
                text(
                    "INSERT INTO users (id,slug,display_name,is_active,created_at,updated_at) VALUES (:id,'synthetic-test','Synthetic',true,now(),now())"
                ),
                {"id": synthetic_user_id},
            )
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM work_access_grants WHERE user_id=:id"),
                    {"id": synthetic_user_id},
                ).scalar_one()
                == 0
            )
            connection.execute(
                text(
                    "INSERT INTO work_workspaces (id,slug,is_active,created_at) VALUES (:id,'synthetic-migration',true,now())"
                ),
                {"id": synthetic_workspace_id},
            )
            connection.execute(
                text(
                    "INSERT INTO work_access_grants (user_id,workspace_id,capability,created_at) VALUES (:user,:workspace,'work_private',now())"
                ),
                {"user": synthetic_user_id, "workspace": synthetic_workspace_id},
            )
        migrate("upgrade", "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT capability FROM work_access_grants WHERE user_id=:user AND workspace_id=:workspace"
                    ),
                    {"user": synthetic_user_id, "workspace": synthetic_workspace_id},
                ).scalar_one()
                == "work_private"
            )

            assert (
                connection.execute(
                    text("SELECT count(*) FROM users WHERE slug='synthetic-test'")
                ).scalar_one()
                == 1
            )
        # A party downgrade may not strand current or historical owner references.
        from datetime import UTC, datetime, timedelta

        from app import work_drafts, work_lifecycle, work_parties

        policy_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO work.retention_policies VALUES(:workspace,:policy,86400)"),
                {"workspace": synthetic_workspace_id, "policy": policy_id},
            )
            driver = connection.connection.driver_connection
            party = work_parties.create(
                driver,
                synthetic_workspace_id,
                policy_id,
                "synthetic:migration-party",
                datetime.now(UTC) + timedelta(hours=1),
            )
            note = work_drafts.create(
                driver,
                synthetic_workspace_id,
                synthetic_user_id,
                policy_id,
                work_lifecycle.Draft(
                    kind="question",
                    marker="synthetic:migration-owned",
                    owner_id=party.id,
                    retain_until=datetime.now(UTC) + timedelta(minutes=30),
                ),
            )
        blocked = subprocess.run(
            ["alembic", "downgrade", "0012_work_confirmations"],
            cwd=backend,
            capture_output=True,
            text=True,
            check=False,
        )
        assert blocked.returncode != 0 and "Forget assigned note histories" in blocked.stderr
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            driver = connection.connection.driver_connection
            # Clearing current owner alone must not erase the previous revision reference.
            corrected = work_drafts.transition(
                driver,
                synthetic_workspace_id,
                synthetic_user_id,
                note.id,
                1,
                "correct",
                work_lifecycle.Draft(
                    kind="question",
                    marker="synthetic:migration-unassigned",
                    retain_until=note.retain_until,
                ),
            )
        blocked = subprocess.run(
            ["alembic", "downgrade", "0012_work_confirmations"],
            cwd=backend,
            capture_output=True,
            text=True,
            check=False,
        )
        assert blocked.returncode != 0 and "Forget assigned note histories" in blocked.stderr
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            work_drafts.transition(
                connection.connection.driver_connection,
                synthetic_workspace_id,
                synthetic_user_id,
                note.id,
                corrected.revision,
                "forget",
            )
        migrate("downgrade", "0012_work_confirmations")
        migrate("upgrade", "head")
        migrate("check")

        # Preserve an existing pre-binding approval as unbound, never silently authorize it.
        migrate("downgrade", "0002_identity")
        legacy_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO approvals (id,scope_key,action_type,status,requested_by,request_payload,requested_at) VALUES (:id,'household_shared','validation.noop','pending','synthetic-legacy','{}'::jsonb,now())"
                ),
                {"id": legacy_id},
            )
        migrate("upgrade", "head")
        migrate("check")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT status,payload_hash,expires_at FROM approvals WHERE id=:id"),
                {"id": legacy_id},
            ).one()
            assert row == ("pending", None, None)
        # Destructive downgrade only inside explicitly opted-in disposable test databases.
        migrate("downgrade", "base")
        assert "users" not in inspect(engine).get_table_names()
        assert "work" not in inspect(engine).get_schema_names()
        migrate("upgrade", "head")
    finally:
        engine.dispose()
