"""Real source dependency redaction, current/history controls and exact authority."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from work_source_helpers import extra_notes, prepare, quarantine
from work_storage_helpers import connect, insert

from app import work_capture, work_drafts, work_lifecycle, work_read
from app import work_source_withdrawal as withdrawal
from app.config import settings
from app.main import app
from app.models import User
from app.work_authority import REGISTRY_KEY
from app.work_capture_storage import provision_captures
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def case(review_case):
    return prepare(review_case)


def request(case, **changes):
    return withdrawal.Request(
        **(
            {
                "database": settings.postgres_db,
                "operator_id": case["actor"],
                "workspace_id": case["workspace"],
                "source_ids": (case["source"],),
            }
            | changes
        )
    )


def run(case, **changes):
    with connect() as db, db.transaction():
        return withdrawal.reconcile(db, request(case, **changes))


def apply(case, plan, **changes):
    return run(
        case,
        **(
            {
                "decision": "withdraw_sources",
                "issued_at": datetime.fromisoformat(plan["issued_at"]),
                "reviewed_hash": plan["reviewed_hash"],
            }
            | changes
        ),
    )


def test_current_history_and_pending_redaction_preserve_unrelated_controls(case):
    quarantine(case)
    plan = run(case)
    notes = {item["id"]: item for item in plan["notes"]}
    assert len(notes) == 2 and len(plan["linked"]) == 4
    assert (
        not notes[str(case["historical"].id)]["current_reference"]
        and notes[str(case["historical"].id)]["historical_reference"]
    )
    assert "synthetic:review-note" not in str(plan) and "pending-source-copy" not in str(plan)
    result = apply(case, plan)
    assert not result["activation_authorized"] and not result["recovery_complete"]
    with connect() as db:
        for record in (case["item"], case["historical"]):
            row = db.execute(
                "SELECT state,snapshot FROM work.drafts WHERE workspace_id=%s AND id=%s",
                (case["workspace"], record.id),
            ).fetchone()
            assert row[0] == "forgotten" and row[1]["marker"] is None and row[1]["source_ids"] == []
            assert not db.execute(
                "SELECT 1 FROM work.draft_revisions WHERE workspace_id=%s AND record_id=%s AND snapshot IS NOT NULL",
                (case["workspace"], record.id),
            ).fetchone()
        for identifier in (case["pending"], case["correction"]):
            assert db.execute(
                "SELECT state,payload,payload_hash FROM work.capture_intents WHERE id=%s",
                (identifier,),
            ).fetchone() == ("denied", None, None)
        assert db.execute(
            "SELECT payload_hash FROM work.draft_reviews WHERE id=%s", (case["review"],)
        ).fetchone() == (None,)
        assert db.execute(
            "SELECT state FROM public.work_confirmation_requests WHERE id=%s",
            (case["confirmation"],),
        ).fetchone() == ("denied",)
        assert db.execute(
            "SELECT state FROM work.capture_intents WHERE id=%s", (case["unrelated"],)
        ).fetchone() == ("pending",)
        assert db.execute(
            "SELECT state FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["control"].id),
        ).fetchone() == ("draft",)
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (False,)
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["other_source"]),
        ).fetchone() == (True,)
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)
    after = run(case)
    assert not after["notes"] and not after["linked"]
    with pytest.raises(ValueError, match="No source"):
        apply(case, after)


def test_source_only_selection_leaves_other_dependencies_untouched(case):
    quarantine(case)
    selected = (case["other_source"],)
    plan = run(case, source_ids=selected)
    assert {item["id"] for item in plan["notes"]} == {
        str(case["control"].id),
        str(case["historical"].id),
    }
    apply(case, plan, source_ids=selected)
    with connect() as db:
        assert db.execute(
            "SELECT state FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone() == ("draft",)
        assert db.execute(
            "SELECT state FROM work.capture_intents WHERE id=%s", (case["pending"],)
        ).fetchone() == ("pending",)


def test_withdrawn_source_cannot_back_new_note_after_explicit_test_activation(case):
    with connect() as db:
        provision_captures(db, case["slug"])
    quarantine(case)
    apply(case, run(case))
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
        )
    with (
        pytest.raises(work_drafts.StoreError, match="Source unavailable"),
        connect() as db,
        db.transaction(),
    ):
        work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:cannot-resurrect",
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
    identifier = uuid4()
    with pytest.raises(psycopg.errors.CheckViolation, match="Draft source denied"), connect() as db:
        db.execute(
            "INSERT INTO work.drafts(workspace_id,id,policy_id,revision,state,retain_until,snapshot) SELECT workspace_id,%s,policy_id,1,'draft',retain_until,snapshot || jsonb_build_object('id',%s::text,'source_ids',jsonb_build_array(%s::text)) FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (
                identifier,
                str(identifier),
                str(case["source"]),
                case["workspace"],
                case["control"].id,
            ),
        )
    with case["maker"].begin() as db:
        administer(db, "grant", case["slug"], db.get(User, case["actor"]).slug)
    app.dependency_overrides[work_capture.get_capture_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    try:
        response = case["client"].post(
            f"/api/v1/work/workspaces/{case['workspace']}/captures",
            headers=case["headers"],
            json={
                "request_id": str(uuid4()),
                "decision": "capture_draft",
                "policy_id": str(case["policy"]),
                "draft": {
                    "kind": "action",
                    "marker": "synthetic:rejected-source",
                    "source_ids": [str(case["source"])],
                    "retain_until": case["control"].retain_until.isoformat(),
                },
            },
        )
        assert response.status_code == 404
        with connect() as db:
            assert db.execute(
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s",
                (case["workspace"],),
            ).fetchone() == (3,)
        control = case["client"].post(
            f"/api/v1/work/workspaces/{case['workspace']}/captures",
            headers=case["headers"],
            json={
                "request_id": str(uuid4()),
                "decision": "capture_draft",
                "policy_id": str(case["policy"]),
                "draft": {
                    "kind": "action",
                    "marker": "synthetic:accepted-other-source",
                    "source_ids": [str(case["other_source"])],
                    "retain_until": case["control"].retain_until.isoformat(),
                },
            },
        )
        assert control.status_code == 202
    finally:
        app.dependency_overrides.pop(work_capture.get_capture_engines, None)


@pytest.mark.parametrize(
    "fault",
    [
        "active",
        "grants",
        "operator",
        "target",
        "workspace",
        "source",
        "isolation",
        "expired",
        "future",
        "hash",
    ],
)
def test_invalid_authority_refuses_without_cleanup(case, fault):
    if fault != "active":
        quarantine(case)
    changes = {}
    if fault == "grants":
        with connect() as db:
            db.execute(
                "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',now())",
                (case["actor"], case["workspace"]),
            )
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "target":
        changes["database"] = "butler_test_wrong"
    if fault == "workspace":
        changes["workspace_id"] = uuid4()
    if fault == "source":
        changes["source_ids"] = (uuid4(),)
    if fault in {"expired", "future"}:
        changes["issued_at"] = datetime.now(UTC) + timedelta(minutes=6 if fault == "future" else -6)
    if fault == "hash":
        changes.update(
            decision="withdraw_sources", issued_at=datetime.now(UTC), reviewed_hash="a" * 64
        )
    with pytest.raises(ValueError), connect() as db, db.transaction():
        if fault == "isolation":
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        withdrawal.reconcile(db, request(case, **changes))
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (True,)
        assert db.execute(
            "SELECT state FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone() == ("draft",)


def test_source_state_drift_invalidates_plan(case):
    quarantine(case)
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        )
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)
    # Already inactive bindings still allow cleanup of their retained derivatives.
    apply(case, run(case))


def test_derived_note_overflow_refuses_entire_withdrawal(case):
    extra_notes(case, 24)
    quarantine(case)
    with pytest.raises(ValueError, match="Too many derived"):
        run(case)


def test_pending_copy_overflow_refuses_entire_withdrawal(case):
    with connect() as db:
        for _ in range(100):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) SELECT workspace_id,actor_id,session_id,%s,payload,clock_timestamp()+interval '4 minutes' FROM work.capture_intents WHERE id=%s",
                (uuid4(), case["pending"]),
            )
    quarantine(case)
    with pytest.raises(ValueError, match="Too many pending"):
        run(case)


def test_receipt_failure_rolls_back_notes_payloads_and_source(case):
    quarantine(case)
    plan = run(case)
    with patch.object(withdrawal, "uuid4", return_value=case["actor"]):
        with connect() as db:
            db.execute(
                "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,result_status) VALUES(%s,now(),'test','system','synthetic','technical_admin','synthetic.collision','success')",
                (case["actor"],),
            )
        with pytest.raises(psycopg.errors.UniqueViolation):
            apply(case, plan)
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (True,)
        assert db.execute(
            "SELECT state,payload IS NOT NULL,payload_hash IS NOT NULL FROM work.capture_intents WHERE id=%s",
            (case["pending"],),
        ).fetchone() == ("pending", True, True)
        assert db.execute(
            "SELECT state FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone() == ("draft",)


def test_registry_and_writer_contention_refuse(case):
    quarantine(case)
    with connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        with pytest.raises(ValueError, match="busy"):
            run(case)
    with connect() as blocker:
        blocker.execute(
            "SELECT id FROM work.drafts WHERE workspace_id=%s FOR UPDATE", (case["workspace"],)
        )
        with pytest.raises(psycopg.errors.LockNotAvailable):
            run(case)


def test_restricted_connection_has_no_cleanup_or_source_mutation(case):
    quarantine(case)
    with pytest.raises(ValueError, match="Clean"), connect() as db, db.transaction():
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        withdrawal.reconcile(db, request(case))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), connect() as db:
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
            (case["workspace"],),
        )


def test_multiple_sources_are_one_reviewed_set(case):
    quarantine(case)
    selection = tuple(sorted((case["source"], case["other_source"])))
    plan = run(case, source_ids=selection)
    assert len(plan["notes"]) == 3
    result = apply(case, plan, source_ids=selection)
    assert len(result["sources"]) == 2


def test_new_dependency_invalidates_prior_plan(case):
    quarantine(case)
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
        )
    extra_notes(case, 1)
    quarantine(case)
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)


def test_postcondition_failure_rolls_back_pending_copy_redaction(case):
    quarantine(case)
    plan = run(case)
    with (
        patch.object(withdrawal.work_drafts, "transition", return_value=None),
        pytest.raises(ValueError, match="invariant"),
    ):
        apply(case, plan)
    with connect() as db:
        assert db.execute(
            "SELECT state,payload IS NOT NULL FROM work.capture_intents WHERE id=%s",
            (case["pending"],),
        ).fetchone() == ("pending", True)
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (True,)


def test_exact_note_and_effect_capacity_is_complete(case):
    extra_notes(case, 23)
    with connect() as db:
        for _ in range(96):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) SELECT workspace_id,actor_id,session_id,%s,payload,clock_timestamp()+interval '4 minutes' FROM work.capture_intents WHERE id=%s",
                (uuid4(), case["pending"]),
            )
    quarantine(case)
    plan = run(case)
    assert len(plan["notes"]) == 25 and len(plan["linked"]) == 100
    result = apply(case, plan)
    assert len(result["forgotten_notes"]) == 25 and len(result["discarded_effects"]) == 100


def test_unused_source_withdrawal_has_no_collateral_cleanup(case):
    source = insert(case["storage"])
    with connect() as db:
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["workspace"], source),
        )
    quarantine(case)
    plan = run(case, source_ids=(source,))
    assert not plan["notes"] and not plan["linked"]
    apply(case, plan, source_ids=(source,))
    with connect() as db:
        assert db.execute(
            "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending'",
            (case["workspace"],),
        ).fetchone() == (3,)
        assert db.execute(
            "SELECT state FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone() == ("draft",)


def test_source_uuid_from_another_workspace_is_not_authority(case):
    foreign = insert(case["storage"], letter="b")
    with connect() as db:
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["storage"]["b"]["workspace"], foreign),
        )
    quarantine(case)
    with pytest.raises(ValueError, match="unavailable"):
        run(case, source_ids=(foreign,))
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["storage"]["b"]["workspace"], foreign),
        ).fetchone() == (True,)
