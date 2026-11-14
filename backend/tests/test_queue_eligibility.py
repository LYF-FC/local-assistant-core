"""Spec 073 rule unit tests: E1–E8 compile to the workers' original conditions.

Each shared rule, compiled for PostgreSQL with literal parameters, must equal the condition the
worker used before the refactor (copied verbatim from ``main`` at 2e04ff8). The PostgreSQL suite
proves the same equivalence on data (test_queue_eligibility_postgres.py).
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.dialects import postgresql

from app import queue_eligibility as eligible
from app.models import (
    FilingExecution,
    JobOutbox,
    NotificationDelivery,
    ReminderPreferences,
    TaskReminder,
)
from app.notifications import IN_FLIGHT_DEADLINE

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
STALE = T - IN_FLIGHT_DEADLINE


def sql(clause):
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_job_rules_match_the_original_claim_condition():
    original = or_(
        (JobOutbox.state == "pending") & (JobOutbox.available_at <= T),
        (JobOutbox.state == "leased") & (JobOutbox.lease_until <= T),
    )
    assert sql(or_(eligible.job_pending(T), eligible.job_lease_expired(T))) == sql(original)


def test_reminder_rule_matches_the_original_candidates_condition():
    original = and_(
        TaskReminder.state == "scheduled",
        TaskReminder.scheduled_at <= T,
        or_(ReminderPreferences.owner_id.is_(None), ReminderPreferences.enabled.is_(True)),
        or_(
            TaskReminder.next_attempt_at <= T,
            TaskReminder.policy_revision != func.coalesce(ReminderPreferences.revision, 0),
        ),
    )
    assert sql(eligible.reminder_due(T)) == sql(original)
    assert sql(eligible.preferences_on_reminder()) == sql(
        ReminderPreferences.owner_id == TaskReminder.owner_id
    )


def test_enqueue_rule_matches_and_has_no_time_input():
    original = and_(TaskReminder.state == "delivered", NotificationDelivery.id.is_(None))
    assert sql(eligible.notification_enqueue_eligible()) == sql(original)
    assert sql(eligible.enqueue_on()) == sql(
        and_(
            NotificationDelivery.reminder_id == TaskReminder.id,
            NotificationDelivery.cycle == TaskReminder.cycle,
        )
    )


def test_notification_rules_are_the_original_condition_distributed():
    paused = or_(
        NotificationDelivery.reason.is_distinct_from("paused"),
        ReminderPreferences.enabled.is_distinct_from(False),
    )
    due = and_(
        NotificationDelivery.state.in_(("pending", "unknown")),
        NotificationDelivery.next_attempt_at <= T,
        NotificationDelivery.attempt_started_at.is_(None),
    )
    expired = and_(
        NotificationDelivery.state == "pending",
        NotificationDelivery.attempt_started_at <= STALE,
    )
    # (P AND A) OR (P AND B) is the original P AND (A OR B); data equivalence is tested on PG.
    assert sql(eligible.notification_due(T)) == sql(and_(paused, *due.clauses))
    assert sql(eligible.notification_in_flight_expired(T)) == sql(and_(paused, *expired.clauses))


def test_filing_rules_match_the_original_candidates_condition():
    original = or_(
        and_(
            FilingExecution.state.in_(("pending", "unknown")),
            FilingExecution.next_attempt_at <= T,
            FilingExecution.attempt_started_at.is_(None),
        ),
        and_(
            FilingExecution.state == "pending",
            FilingExecution.attempt_started_at <= STALE,
        ),
    )
    assert sql(or_(eligible.filing_due(T), eligible.filing_in_flight_expired(T))) == sql(original)


def test_shared_rules_never_contain_observer_guards():
    for rule in (
        eligible.job_pending(T),
        eligible.job_lease_expired(T),
        eligible.reminder_due(T),
        eligible.notification_enqueue_eligible(),
        eligible.notification_due(T),
        eligible.notification_in_flight_expired(T),
        eligible.filing_due(T),
        eligible.filing_in_flight_expired(T),
    ):
        text = sql(rule)
        assert "updated_at" not in text and "delivered_at" not in text
