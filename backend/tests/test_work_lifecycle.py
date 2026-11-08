from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import work_lifecycle as lifecycle
from app.work_access import PENDING_GATES

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
WORKSPACE, ACTOR, SOURCE = uuid4(), uuid4(), uuid4()


def policy(workspace=WORKSPACE):
    return lifecycle.RetentionPolicy(
        workspace_id=workspace, policy_id=uuid4(), max_age_seconds=86400
    )


def draft(**changes):
    values = {
        "kind": "action",
        "marker": "synthetic:review-note",
        "source_ids": (SOURCE,),
        "retain_until": NOW + timedelta(hours=1),
    }
    values.update(changes)
    return lifecycle.Draft(**values)


def create(**changes):
    return lifecycle.create(draft(**changes), WORKSPACE, ACTOR, policy(), NOW, record_id=uuid4())


def test_create_preserves_unknowns_and_immutable_snapshots_without_execution():
    history = create(source_ids=())
    item = history[0]
    assert item.state == "draft" and item.revision == 1
    assert item.owner_id is None and item.due_at is None and item.source_ids == ()
    assert item.model_dump(mode="json")["owner_id"] is None
    assert "synthetic:review-note" not in repr(item)
    with pytest.raises(ValidationError):
        item.state = "confirmed"
    with pytest.raises(TypeError):
        history[0] = item


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", WORKSPACE),
        ("actor_id", ACTOR),
        ("state", "confirmed"),
        ("revision", 1),
        ("scope", "household_shared"),
        ("sql", "SELECT 1"),
        ("execution_allowed", True),
    ],
)
def test_payload_cannot_choose_server_identity_state_or_execution(field, value):
    with pytest.raises(ValidationError):
        draft(**{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"marker": "real-content"},
        {"marker": "synthetic:a\n"},
        {"marker": "synthetic:" + "x" * 256},
        {"source_ids": (SOURCE, SOURCE)},
        {"source_ids": tuple(uuid4() for _ in range(11))},
        {"retain_until": NOW.replace(tzinfo=None)},
        {"due_at": NOW.replace(tzinfo=None)},
    ],
)
def test_invalid_content_source_and_dates_are_rejected(changes):
    with pytest.raises(ValidationError):
        draft(**changes)


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_policy",
        "expired",
        "over_policy",
        "naive_clock",
        "untyped_workspace",
        "untyped_actor",
    ],
)
def test_creation_requires_explicit_policy_binding_and_server_metadata(fault):
    payload, workspace, actor, chosen_policy, now = draft(), WORKSPACE, ACTOR, policy(), NOW
    if fault == "foreign_policy":
        chosen_policy = policy(uuid4())
    elif fault == "expired":
        payload = draft(retain_until=NOW)
    elif fault == "over_policy":
        payload = draft(retain_until=NOW + timedelta(days=2))
    elif fault == "naive_clock":
        now = NOW.replace(tzinfo=None)
    elif fault == "untyped_workspace":
        workspace = str(workspace)
    elif fault == "untyped_actor":
        actor = str(actor)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.create(payload, workspace, actor, chosen_policy, now, record_id=uuid4())


def test_confirmation_correction_requires_new_review_without_extending_retention():
    first = create()
    confirmed = lifecycle.confirm(first, WORKSPACE, ACTOR, 1, NOW)
    assert confirmed[-1].state == "confirmed" and first[-1].state == "draft"
    corrected = lifecycle.correct(
        confirmed,
        draft(marker="synthetic:corrected", owner_id=None, due_at=None),
        WORKSPACE,
        ACTOR,
        2,
        NOW + timedelta(minutes=1),
    )
    assert corrected[-1].state == "draft" and corrected[-1].revision == 3
    assert corrected[1].marker == "synthetic:review-note"
    assert corrected[-1].owner_id is None and corrected[-1].due_at is None
    assert lifecycle.export_preview((corrected,), WORKSPACE, NOW + timedelta(minutes=1)).items == ()
    reviewed = lifecycle.confirm(corrected, WORKSPACE, ACTOR, 3, NOW + timedelta(minutes=1))
    export = lifecycle.export_preview((reviewed,), WORKSPACE, NOW + timedelta(minutes=1))
    assert len(export.items) == 1 and export.items[0].marker == "synthetic:corrected"
    assert export.execution_allowed is False and export.persistent_export is False


@pytest.mark.parametrize(
    "fault",
    [
        "stale",
        "boolean_revision",
        "foreign_workspace",
        "backward_clock",
        "ungrounded",
        "double_confirm",
        "expired",
    ],
)
def test_confirmation_refuses_invalid_transitions(fault):
    history, workspace, revision, now = create(), WORKSPACE, 1, NOW
    if fault == "stale":
        revision = 2
    elif fault == "boolean_revision":
        revision = True
    elif fault == "foreign_workspace":
        workspace = uuid4()
    elif fault == "backward_clock":
        now = NOW - timedelta(seconds=1)
    elif fault == "ungrounded":
        history = create(source_ids=())
    elif fault == "double_confirm":
        history = lifecycle.confirm(history, WORKSPACE, ACTOR, 1, NOW)
        revision = 2
    elif fault == "expired":
        now = NOW + timedelta(hours=1)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.confirm(history, workspace, ACTOR, revision, now)


@pytest.mark.parametrize(
    "changes",
    [{"kind": "decision"}, {"retain_until": NOW + timedelta(hours=2)}, {"retain_until": NOW}],
)
def test_correction_cannot_reclassify_or_extend_or_expire_retention(changes):
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.correct(create(), draft(**changes), WORKSPACE, ACTOR, 1, NOW)


def test_forget_projects_all_revision_payloads_and_is_terminal_even_after_expiry():
    history = lifecycle.confirm(create(), WORKSPACE, ACTOR, 1, NOW)
    result = lifecycle.forget(history, WORKSPACE, ACTOR, 2, NOW + timedelta(hours=2))
    assert len(result) == 3 and result[-1].revision == 3
    for item in result:
        assert item.state == "forgotten" and item.marker is None and item.source_ids == ()
        assert item.owner_id is None and item.due_at is None and item.retain_until is None
    assert history[0].marker == "synthetic:review-note"  # projection cannot erase prior references
    assert lifecycle.forget(result, WORKSPACE, ACTOR, 3, NOW + timedelta(hours=2)) is result
    for operation in (
        lambda: lifecycle.confirm(result, WORKSPACE, ACTOR, 3, NOW + timedelta(hours=2)),
        lambda: lifecycle.correct(result, draft(), WORKSPACE, ACTOR, 3, NOW + timedelta(hours=2)),
    ):
        with pytest.raises(lifecycle.LifecycleError):
            operation()
    assert (
        lifecycle.export_preview(
            (result,), WORKSPACE, NOW + timedelta(hours=2), include_drafts=True
        ).items
        == ()
    )


def test_history_bound_never_prevents_terminal_forgetting():
    history = create()
    for revision in range(1, 100):
        history = lifecycle.correct(history, draft(), WORKSPACE, ACTOR, revision, NOW)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.correct(history, draft(), WORKSPACE, ACTOR, 100, NOW)
    result = lifecycle.forget(history, WORKSPACE, ACTOR, 100, NOW)
    assert len(result) == 101 and lifecycle.export_preview((result,), WORKSPACE, NOW).items == ()


@pytest.mark.parametrize(
    "fault",
    [
        "foreign",
        "out_of_order",
        "wrong_record",
        "partial_redaction",
        "retention_extension",
        "confirmation_change",
        "empty",
        "not_record",
    ],
)
def test_inconsistent_history_is_never_exported(fault):
    first = create()
    confirmed = lifecycle.confirm(first, WORKSPACE, ACTOR, 1, NOW)
    if fault == "foreign":
        history = (
            lifecycle.Record.model_validate(dict(first[0].model_dump(), workspace_id=uuid4())),
        )
    elif fault == "out_of_order":
        history = tuple(reversed(confirmed))
    elif fault == "wrong_record":
        history = (
            first[0],
            lifecycle.Record.model_validate(dict(confirmed[-1].model_dump(), id=uuid4())),
        )
    elif fault == "partial_redaction":
        forgotten = lifecycle.forget(first, WORKSPACE, ACTOR, 1, NOW)
        history = (first[0], forgotten[-1])
    elif fault == "retention_extension":
        history = (
            first[0],
            lifecycle.Record.model_validate(
                dict(confirmed[-1].model_dump(), retain_until=NOW + timedelta(hours=2))
            ),
        )
    elif fault == "confirmation_change":
        history = (
            first[0],
            lifecycle.Record.model_validate(
                dict(confirmed[-1].model_dump(), marker="synthetic:tampered")
            ),
        )
    elif fault == "empty":
        history = ()
    else:
        history = (object(),)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.export_preview((history,), WORKSPACE, NOW, include_drafts=True)


def test_export_is_bounded_current_only_and_expires_at_boundary():
    history = create()
    assert lifecycle.export_preview((history,), WORKSPACE, NOW).items == ()
    assert (
        lifecycle.export_preview((history,), WORKSPACE, NOW, include_drafts=True).items == history
    )
    assert (
        lifecycle.export_preview(
            (history,), WORKSPACE, NOW + timedelta(hours=1), include_drafts=True
        ).items
        == ()
    )
    for selected in ((history, history), tuple(create() for _ in range(26))):
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.export_preview(selected, WORKSPACE, NOW)


def test_contracts_do_not_open_work_content_or_change_pending_gates(auth_client):
    assert len(PENDING_GATES) == 5
    assert (
        auth_client.post(f"/api/v1/work/workspaces/{WORKSPACE}/records", json={}).status_code == 404
    )
    assert (
        auth_client.post(f"/api/v1/work/workspaces/{WORKSPACE}/debriefs", json={}).status_code
        == 404
    )
