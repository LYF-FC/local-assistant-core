"""Trusted local synthetic persistence primitives; no API or human authority token."""

from uuid import UUID, uuid4

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from app import work_lifecycle as lifecycle
from app.config import settings
from app.work_authority import REGISTRY_KEY


class StoreError(ValueError):
    pass


def _begin(
    db, workspace_id: UUID, actor_id: UUID, *, maintenance: bool = False, restore: bool = False
) -> None:
    if (
        settings.env not in {"development", "test"}
        or (settings.env == "test" and not settings.postgres_db.startswith("butler_test"))
        or type(maintenance) is not bool
        or type(restore) is not bool
        or (maintenance and restore)
        or not isinstance(workspace_id, UUID)
        or not isinstance(actor_id, UUID)
        or db.info.transaction_status != TransactionStatus.INTRANS
    ):
        raise StoreError("Explicit local synthetic transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'), "
        "current_user=pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.drafts'::regclass"
    ).fetchone()
    if profile != (True, "read committed", True):
        raise StoreError("Clean local storage owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    if maintenance or restore:
        db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        if restore:
            db.execute("SET LOCAL butler.restore_suppression='reviewed'")
            if not db.execute(
                "SELECT work.restore_suppression_allowed(%s)", (workspace_id,)
            ).fetchone()[0]:
                raise StoreError("Quarantined restore required")
        else:
            db.execute("SET LOCAL butler.retention_cleanup='expired'")
    else:
        db.execute("SELECT pg_advisory_xact_lock_shared(%s,%s)", REGISTRY_KEY)
    if not db.execute(
        "SELECT 1 FROM public.work_workspaces WHERE id=%s AND is_active=%s AND slug LIKE 'synthetic-%%'",
        (workspace_id, not (maintenance or restore)),
    ).fetchone():
        raise StoreError("Synthetic workspace unavailable")


def _now(db):
    return db.execute("SELECT clock_timestamp()").fetchone()[0]


def _record(value) -> lifecycle.Record:
    return lifecycle.Record.model_validate(value)


def _sources(db, workspace_id, record):
    if record.source_ids:
        rows = db.execute(
            "SELECT id FROM work.source_registry WHERE workspace_id=%s AND is_active AND id=ANY(%s) ORDER BY id FOR SHARE",
            (workspace_id, list(record.source_ids)),
        ).fetchall()
        if {row[0] for row in rows} != set(record.source_ids):
            raise StoreError("Source unavailable")


def _owner(db, workspace_id, owner_id):
    if (
        owner_id is not None
        and not db.execute(
            "SELECT 1 FROM work.parties WHERE workspace_id=%s AND id=%s AND state='active' AND retain_until>clock_timestamp() FOR SHARE",
            (workspace_id, owner_id),
        ).fetchone()
    ):
        raise StoreError("Active workspace party required")


def _history(db, workspace_id, record_id):
    if not isinstance(record_id, UUID):
        raise StoreError("Typed record identity required")
    row = db.execute(
        "SELECT snapshot FROM work.drafts WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (workspace_id, record_id),
    ).fetchone()
    if row is None:
        raise StoreError("Draft unavailable")
    current = _record(row[0])
    rows = db.execute(
        "SELECT revision,actor_id,occurred_at,snapshot FROM work.draft_revisions WHERE workspace_id=%s AND record_id=%s ORDER BY revision",
        (workspace_id, record_id),
    ).fetchall()
    history = tuple(
        _record(snapshot)
        if snapshot is not None
        else _record(dict(current.model_dump(), revision=revision, actor_id=actor, updated_at=at))
        for revision, actor, at, snapshot in rows
    )
    if not history or history[-1] != current:
        raise StoreError("Draft history unavailable")
    return history


def create(db, workspace_id: UUID, actor_id: UUID, policy_id: UUID, payload: lifecycle.Draft):
    _begin(db, workspace_id, actor_id)
    if not isinstance(policy_id, UUID):
        raise StoreError("Typed policy identity required")
    row = db.execute(
        "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=%s AND id=%s FOR SHARE",
        (workspace_id, policy_id),
    ).fetchone()
    if row is None:
        raise StoreError("Explicit policy unavailable")
    policy = lifecycle.RetentionPolicy(
        workspace_id=workspace_id, policy_id=policy_id, max_age_seconds=row[0]
    )
    item = lifecycle.create(payload, workspace_id, actor_id, policy, _now(db), record_id=uuid4())[
        -1
    ]
    _sources(db, workspace_id, item)
    _owner(db, workspace_id, item.owner_id)
    row = db.execute(
        "INSERT INTO work.drafts(workspace_id,id,policy_id,revision,state,retain_until,snapshot) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING snapshot",
        (
            workspace_id,
            item.id,
            policy_id,
            item.revision,
            item.state,
            item.retain_until,
            Jsonb(item.model_dump(mode="json")),
        ),
    ).fetchone()
    return _record(row[0])


def transition(
    db,
    workspace_id: UUID,
    actor_id: UUID,
    record_id: UUID,
    expected_revision: int,
    action: str,
    payload: lifecycle.Draft | None = None,
    *,
    maintenance: bool = False,
    restore: bool = False,
):
    if (maintenance or restore) and (action != "forget" or payload is not None):
        raise StoreError("Maintenance only forgets expired records")
    _begin(db, workspace_id, actor_id, maintenance=maintenance, restore=restore)
    history = _history(db, workspace_id, record_id)
    now = _now(db)
    if maintenance and (history[-1].retain_until is None or history[-1].retain_until > now):
        raise StoreError("Maintenance requires an expired live record")
    if action == "correct" and isinstance(payload, lifecycle.Draft):
        proposed = lifecycle.correct(
            history, payload, workspace_id, actor_id, expected_revision, now
        )
    elif action == "confirm" and payload is None:
        proposed = lifecycle.confirm(history, workspace_id, actor_id, expected_revision, now)
    elif action == "forget" and payload is None:
        proposed = lifecycle.forget(history, workspace_id, actor_id, expected_revision, now)
    else:
        raise StoreError("Unsupported draft operation")
    item = proposed[-1]
    if proposed is history:
        return item
    if item.state != "forgotten":
        _sources(db, workspace_id, item)
        _owner(db, workspace_id, item.owner_id)
    row = db.execute(
        "UPDATE work.drafts SET revision=%s,state=%s,retain_until=%s,snapshot=%s WHERE workspace_id=%s AND id=%s AND revision=%s RETURNING snapshot",
        (
            item.revision,
            item.state,
            item.retain_until,
            Jsonb(item.model_dump(mode="json")),
            workspace_id,
            record_id,
            expected_revision,
        ),
    ).fetchone()
    if row is None:
        raise StoreError("Stale revision")
    return _record(row[0])


def read(db, workspace_id: UUID, actor_id: UUID, record_id: UUID):
    _begin(db, workspace_id, actor_id)
    history = _history(db, workspace_id, record_id)
    current = history[-1]
    if current.state == "forgotten":
        raise StoreError("Draft unavailable")
    _sources(db, workspace_id, current)
    result = lifecycle.export_preview((history,), workspace_id, _now(db), include_drafts=True)
    if not result.items:
        raise StoreError("Draft unavailable")
    db.execute(
        "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(%s,%s,%s,%s,'draft.read_prepared')",
        (workspace_id, record_id, current.revision, actor_id),
    )
    # This value is prepared inside the caller's transaction, not delivered/committed.
    final = lifecycle.export_preview((history,), workspace_id, _now(db), include_drafts=True)
    if not final.items:
        raise StoreError("Draft unavailable")
    return final
