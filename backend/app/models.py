import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Scope(Base):
    __tablename__ = "scopes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserScope(Base):
    __tablename__ = "user_scopes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scopes.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    request_payload: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_scope_key", "scope_key"),
        Index("ix_audit_events_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    initiator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    initiator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    worker: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True
    )
    source_context: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    before_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_runtime: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)


class Credential(Base):
    __tablename__ = "auth_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthRateWindow(Base):
    __tablename__ = "auth_rate_windows"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class DurableJob(Base):
    __tablename__ = "durable_jobs"
    __table_args__ = (
        UniqueConstraint("requested_by", "idempotency_hash", name="uq_job_request_key"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','dead_letter')", name="ck_job_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), unique=True, nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobOutbox(Base):
    __tablename__ = "job_outbox"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','leased','done','dead_letter')", name="ck_outbox_state"
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="ck_outbox_attempts"),
        CheckConstraint(
            "(state = 'leased' AND lease_hash IS NOT NULL AND lease_until IS NOT NULL) OR (state <> 'leased' AND lease_hash IS NULL AND lease_until IS NULL)",
            name="ck_outbox_lease",
        ),
        Index("ix_outbox_ready", "state", "available_at", "lease_until"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("durable_jobs.id"), nullable=False, unique=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    lease_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


MEMORY_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class MemoryRecord(Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_memory_revision"),
        CheckConstraint(
            "kind IN ('profile','preference','experience','procedure','context')",
            name="ck_memory_kind",
        ),
        CheckConstraint("state IN ('active','forgotten')", name="ck_memory_state"),
        CheckConstraint(
            "(state='active' AND title IS NOT NULL AND content IS NOT NULL AND source_type IS NOT NULL AND source_reference IS NOT NULL AND assessment IS NOT NULL AND assessment IN ('confirmed','tentative')) OR (state='forgotten' AND title IS NULL AND content IS NULL AND source_type IS NULL AND source_reference IS NULL AND assessment IS NULL AND expires_at IS NULL)",
            name="ck_memory_content",
        ),
        CheckConstraint(
            "state='forgotten' OR kind<>'context' OR expires_at IS NOT NULL",
            name="ck_memory_context_expiry",
        ),
        Index("ix_memory_scope_owner_id", "scope_key", "owner_id", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    content: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    assessment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MemoryRevision(Base):
    __tablename__ = "memory_revisions"
    __table_args__ = (
        UniqueConstraint("memory_id", "revision", name="uq_memory_revision"),
        CheckConstraint("revision >= 1", name="ck_memory_history_revision"),
        Index("ix_memory_history", "memory_id", "revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memory_records.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class WorkWorkspace(Base):
    """Identity registry only. Never store employer content in this table."""

    __tablename__ = "work_workspaces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class WorkGrant(Base):
    __tablename__ = "work_access_grants"
    __table_args__ = (CheckConstraint("capability = 'work_private'", name="ck_work_capability"),)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("work_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(String(32), nullable=False, default="work_private")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class WorkConfirmationRequest(Base):
    """Metadata queue only; content and consumption stay in private work storage."""

    __tablename__ = "work_confirmation_requests"
    __table_args__ = (
        UniqueConstraint("workspace_id", "actor_id", "session_id", "request_id"),
        UniqueConstraint("workspace_id", "review_preparation_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_preparation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reviewed_revision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    applied_revision: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ManualTask(Base):
    """Human-controlled agenda, independent of legacy execution tasks."""

    __tablename__ = "manual_tasks"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_manual_task_revision"),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_manual_task_scope",
        ),
        CheckConstraint("state IN ('active','forgotten')", name="ck_manual_task_state"),
        CheckConstraint(
            "assignee_id IS NULL OR assignee_id=owner_id", name="ck_manual_task_assignee"
        ),
        CheckConstraint(
            "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND details IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND status IN ('open','done','cancelled') AND status IS NOT NULL AND ((status='open' AND completed_at IS NULL AND cancelled_at IS NULL) OR (status='done' AND completed_at IS NOT NULL AND cancelled_at IS NULL) OR (status='cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL))) OR (state='forgotten' AND title IS NULL AND details IS NULL AND source_reference IS NULL AND status IS NULL AND due_at IS NULL AND assignee_id IS NULL AND completed_at IS NULL AND cancelled_at IS NULL)",
            name="ck_manual_task_content",
        ),
        Index("ix_manual_task_scope_owner", "scope_key", "owner_id", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    details: Mapped[str | None] = mapped_column(String(4000))
    source_reference: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(16))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ManualTaskRevision(Base):
    __tablename__ = "manual_task_revisions"
    __table_args__ = (
        UniqueConstraint("task_id", "revision", name="uq_manual_task_revision"),
        CheckConstraint("revision >= 1", name="ck_manual_task_history_revision"),
        CheckConstraint(
            "operation IN ('created','corrected','completed','cancelled','reopened','forgotten')",
            name="ck_manual_task_operation",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("manual_tasks.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskReminder(Base):
    __tablename__ = "task_reminders"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_task_reminder_task"),
        CheckConstraint(
            "revision>=1 AND cycle>=1 AND policy_revision>=0 AND task_revision>=1",
            name="ck_reminder_versions",
        ),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_reminder_scope",
        ),
        CheckConstraint(
            "state IN ('scheduled','delivered','acknowledged','cancelled')",
            name="ck_reminder_state",
        ),
        CheckConstraint(
            "(state='scheduled' AND next_attempt_at IS NOT NULL AND next_attempt_at>=scheduled_at AND delivered_at IS NULL) OR (state IN ('delivered','acknowledged') AND next_attempt_at IS NULL AND delivered_at IS NOT NULL) OR (state='cancelled' AND next_attempt_at IS NULL)",
            name="ck_reminder_delivery",
        ),
        CheckConstraint(
            "reason IS NULL OR reason IN ('quiet_hours','daily_limit','owner_unavailable','scope_unavailable','task_closed','task_forgotten','cancelled_by_owner')",
            name="ck_reminder_reason",
        ),
        Index("ix_reminder_due", "state", "next_attempt_at", "id"),
        Index("ix_reminder_owner_scope", "owner_id", "scope_key", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("manual_tasks.id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    task_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskReminderEvent(Base):
    __tablename__ = "task_reminder_events"
    __table_args__ = (
        UniqueConstraint("reminder_id", "revision", name="uq_reminder_event_revision"),
        CheckConstraint("revision>=1", name="ck_reminder_event_revision"),
        CheckConstraint(
            "operation IN ('scheduled','rescheduled','delivered','deferred','acknowledged','cancelled')",
            name="ck_reminder_event_operation",
        ),
        Index("ix_reminder_deliveries", "owner_id", "operation", "recorded_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reminder_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("task_reminders.id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)


class ReminderPreferences(Base):
    __tablename__ = "reminder_preferences"
    __table_args__ = (
        CheckConstraint(
            "revision>=1 AND daily_limit BETWEEN 1 AND 20 AND quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439",
            name="ck_reminder_preferences",
        ),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    quiet_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quiet_end: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentRecord(Base):
    __tablename__ = "document_records"
    __table_args__ = (
        CheckConstraint("revision>=1", name="ck_document_revision"),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_document_scope",
        ),
        CheckConstraint("state IN ('active','forgotten')", name="ck_document_state"),
        CheckConstraint(
            "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND filename IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND content_text IS NOT NULL AND length(content_text) BETWEEN 0 AND 32000 AND sha256 IS NOT NULL AND length(sha256)=64 AND byte_size IS NOT NULL AND byte_size BETWEEN 1 AND 131072 AND reviewed IS NOT NULL AND ((extraction_json IS NULL AND length(content_text)>=1) OR (extraction_json IS NOT NULL AND (reviewed=false OR extraction_json ->> 'status'='ready'))) AND ((ingest_key IS NULL AND ingest_hash IS NULL) OR (ingest_key IS NOT NULL AND ingest_hash IS NOT NULL AND length(ingest_hash)=64))) OR (state='forgotten' AND title IS NULL AND filename IS NULL AND source_reference IS NULL AND content_text IS NULL AND sha256 IS NULL AND byte_size IS NULL AND reviewed IS NULL AND extraction_json IS NULL AND ingest_hash IS NULL)",
            name="ck_document_content",
        ),
        Index("ix_document_scope_owner", "scope_key", "owner_id", "id"),
        UniqueConstraint("owner_id", "ingest_key", name="uq_document_ingest_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    filename: Mapped[str | None] = mapped_column(String(120))
    source_reference: Mapped[str | None] = mapped_column(String(512))
    content_text: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    reviewed: Mapped[bool | None] = mapped_column(Boolean)
    extraction_json: Mapped[dict | None] = mapped_column(MEMORY_JSON)
    ingest_key: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    ingest_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_document_version"),
        CheckConstraint("revision>=1", name="ck_document_version_revision"),
        CheckConstraint(
            "operation IN ('uploaded','corrected','replaced','extracted','forgotten')",
            name="ck_document_operation",
        ),
        CheckConstraint(
            "(snapshot IS NULL AND original_bytes IS NULL) OR (snapshot IS NOT NULL AND original_bytes IS NOT NULL)",
            name="ck_document_version_content",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_records.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON)
    original_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentArchiveBinding(Base):
    __tablename__ = "document_archive_bindings"
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_records.id"), primary_key=True
    )
    root_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalendarSource(Base):
    __tablename__ = "calendar_sources"
    __table_args__ = (
        CheckConstraint("revision BETWEEN 1 AND 101", name="ck_calendar_revision"),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_calendar_scope",
        ),
        CheckConstraint(
            "(state='active' AND data IS NOT NULL) OR (state='forgotten' AND data IS NULL)",
            name="ck_calendar_content",
        ),
        Index("ix_calendar_scope_owner", "scope_key", "owner_id", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalendarRevision(Base):
    __tablename__ = "calendar_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "revision", name="uq_calendar_revision"),
        CheckConstraint("revision BETWEEN 1 AND 101", name="ck_calendar_history_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calendar_sources.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Routine(Base):
    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint(
            "revision BETWEEN 1 AND 1000 AND changes BETWEEN 0 AND 102 AND position BETWEEN 0 AND 366",
            name="ck_routine_versions",
        ),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_routine_scope",
        ),
        CheckConstraint(
            "(state='active' AND data IS NOT NULL AND next_at IS NOT NULL) OR (state IN ('paused','finished','blocked') AND data IS NOT NULL AND next_at IS NULL) OR (state='forgotten' AND data IS NULL AND next_at IS NULL)",
            name="ck_routine_content",
        ),
        Index("ix_routine_due", "state", "next_at", "id"),
        Index("ix_routine_scope_owner", "scope_key", "owner_id", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoutineRevision(Base):
    __tablename__ = "routine_revisions"
    __table_args__ = (UniqueConstraint("routine_id", "revision", name="uq_routine_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routine_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("routines.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoutineOccurrence(Base):
    __tablename__ = "routine_occurrences"
    __table_args__ = (
        UniqueConstraint("routine_id", "local_date", name="uq_routine_local_date"),
        UniqueConstraint("task_id", name="uq_routine_task"),
        CheckConstraint("routine_revision>=1", name="ck_routine_occurrence_revision"),
        CheckConstraint(
            "(outcome='created' AND task_id IS NOT NULL AND due_at IS NOT NULL) OR (outcome='missed' AND task_id IS NULL AND due_at IS NOT NULL) OR (outcome='dst_gap' AND task_id IS NULL AND due_at IS NULL)",
            name="ck_routine_outcome",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routine_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("routines.id"), nullable=False
    )
    routine_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    local_date: Mapped[str] = mapped_column(String(10), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("manual_tasks.id")
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceReview(Base):
    __tablename__ = "invoice_reviews"
    __table_args__ = (
        CheckConstraint(
            "revision BETWEEN 1 AND 101 AND source_revision>=1", name="ck_invoice_revision"
        ),
        CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_invoice_scope",
        ),
        CheckConstraint(
            "(state IN ('draft','reviewed') AND data IS NOT NULL) OR (state='forgotten' AND data IS NULL AND issuer_key IS NULL AND number_key IS NULL)",
            name="ck_invoice_content",
        ),
        CheckConstraint(
            "state='reviewed' OR (issuer_key IS NULL AND number_key IS NULL)",
            name="ck_invoice_keys",
        ),
        Index("ix_invoice_match", "scope_key", "issuer_key", "number_key", "document_id"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_records.id"), primary_key=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(96), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    issuer_key: Mapped[str | None] = mapped_column(String(512))
    number_key: Mapped[str | None] = mapped_column(String(288))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceRevision(Base):
    __tablename__ = "invoice_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision", name="uq_invoice_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoice_reviews.document_id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    snapshot: Mapped[dict | None] = mapped_column(MEMORY_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
