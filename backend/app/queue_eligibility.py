"""Shared worker eligibility rules E1–E8 (spec 073).

Each function restates, exactly, one condition that a worker uses today to select work, with the
worker's ``now`` replaced by the cutoff ``t``. Workers call them with their own single ``now`` and
keep their joins, ordering, limits and locks, so selection is unchanged. The operations observer
calls the same functions with an earlier cutoff and adds its own eligible-since guards; those
guards live only in ``app.operations`` and must never be added here.

Callers must provide the joins the rules refer to:

* E3, E5, E6: ``LEFT JOIN reminder_preferences`` on the row owner (``preferences_on_*``).
* E4: ``LEFT JOIN notification_deliveries`` on reminder and cycle (``enqueue_on``).

The in-flight deadlines are read from their modules at call time, so a test that adjusts them
affects workers and the observer alike.
"""

from sqlalchemy import and_, func, or_

from app import filing
from app import notifications as notes
from app.models import (
    FilingExecution,
    JobOutbox,
    NotificationDelivery,
    ReminderPreferences,
    TaskReminder,
)


def preferences_on_reminder():
    return ReminderPreferences.owner_id == TaskReminder.owner_id


def preferences_on_delivery():
    return ReminderPreferences.owner_id == NotificationDelivery.owner_id


def enqueue_on():
    return and_(
        NotificationDelivery.reminder_id == TaskReminder.id,
        NotificationDelivery.cycle == TaskReminder.cycle,
    )


def job_pending(t):
    """E1: a pending approved job whose availability time has passed."""
    return (JobOutbox.state == "pending") & (JobOutbox.available_at <= t)


def job_lease_expired(t):
    """E2: a leased approved job whose lease has expired."""
    return (JobOutbox.state == "leased") & (JobOutbox.lease_until <= t)


def reminder_due(t):
    """E3: a scheduled reminder that is due, or whose owner's policy revision changed."""
    return and_(
        TaskReminder.state == "scheduled",
        TaskReminder.scheduled_at <= t,
        or_(ReminderPreferences.owner_id.is_(None), ReminderPreferences.enabled.is_(True)),
        or_(
            TaskReminder.next_attempt_at <= t,
            TaskReminder.policy_revision != func.coalesce(ReminderPreferences.revision, 0),
        ),
    )


def notification_enqueue_eligible():
    """E4: a delivered reminder cycle without a delivery. It has no time input."""
    return and_(TaskReminder.state == "delivered", NotificationDelivery.id.is_(None))


def _not_paused():
    # A delivery parked as paused stays out of the due set until its owner resumes.
    return or_(
        NotificationDelivery.reason.is_distinct_from("paused"),
        ReminderPreferences.enabled.is_distinct_from(False),
    )


def notification_due(t):
    """E5: a pending or unknown delivery whose next attempt is due and that is not in flight."""
    return and_(
        _not_paused(),
        NotificationDelivery.state.in_(("pending", "unknown")),
        NotificationDelivery.next_attempt_at <= t,
        NotificationDelivery.attempt_started_at.is_(None),
    )


def notification_in_flight_expired(t):
    """E6: a pending delivery whose attempt started before the in-flight deadline."""
    return and_(
        _not_paused(),
        NotificationDelivery.state == "pending",
        NotificationDelivery.attempt_started_at <= t - notes.IN_FLIGHT_DEADLINE,
    )


def filing_due(t):
    """E7: a pending or unknown filing whose next attempt is due and that is not in flight."""
    return and_(
        FilingExecution.state.in_(("pending", "unknown")),
        FilingExecution.next_attempt_at <= t,
        FilingExecution.attempt_started_at.is_(None),
    )


def filing_in_flight_expired(t):
    """E8: a pending filing whose attempt started before the in-flight deadline."""
    return and_(
        FilingExecution.state == "pending",
        FilingExecution.attempt_started_at <= t - filing.IN_FLIGHT_DEADLINE,
    )
