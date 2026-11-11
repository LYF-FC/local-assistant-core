# Synthetic notification path — spec 068

A delivered in-app reminder ([task reminders](TASK_REMINDERS.md)) can be handed to a **synthetic channel**. This is development/test engineering that proves delivery semantics before any real connector exists. Nothing is sent to a phone, an email address, a provider or the internet. A *delivered* notification here means the synthetic channel accepted it, not that a person saw it.

## States

| State | Meaning |
|---|---|
| pending | Waiting for its next allowed attempt (reason may be `quiet_hours`, `daily_limit`, `transient_error` or `reconciled_absent`). |
| unknown | An attempt may or may not have reached the channel. Only a lookup resolves it; it is never resent blindly. |
| delivered | Accepted by the channel, or found there by reconciliation. Terminal. |
| failed | Rejected, or three attempts used. Terminal. |
| cancelled | The reminder was acknowledged/cancelled/rescheduled, the owner became inactive or the scope grant was removed. Terminal. |

One delivery exists per reminder **cycle**. Rescheduling a delivered reminder starts a new cycle and a new delivery; the old one is cancelled if it had not finished.

## Rules

- **Recipient.** Each delivery stores an opaque alias (`synthetic:` plus a hash of the owner ID). No name, address or device is stored. Owner and scope must still be active and granted when an attempt starts.
- **Quiet hours, pause and day budget** reuse your reminder preferences. The day count uses recorded notification deliveries in your local day, including reconciled ones. Deferral keeps the delivery and records the reason and next check.
- **Pause.** While your reminder preferences are paused, a due delivery is parked once: it stays `pending` with reason `paused` (it is never cancelled), one history entry is written, and it is left out of the worker's due set, so a paused owner neither repeats work on every pass nor delays anyone else's deliveries. When you resume, it is eligible again on the next pass and no new delivery is created. An unknown outcome is still reconciled by lookup while paused, because that never sends anything.
- **Retry.** At most three attempts. After a transient error the next attempt waits 1, then 5, then 15 minutes. A rejection fails immediately.
- **Ambiguity.** The attempt is committed before sending. A timeout, an unexpected channel error, or a claim left for over five minutes (the process died) becomes `unknown`. A lookup keyed by the delivery ID then decides: found means delivered, absent allows one bounded retry, unavailable keeps it `unknown` and polls every 15 minutes. The delivery is not resent while its outcome is unknown.
- **Privacy.** Deliveries, history and audit hold identifiers, states, counts and times only, never task text.

## Reading your deliveries

`POST /api/v1/notifications/query` (scope, optional state filter, cursor; 25 per page) and `POST /api/v1/notifications/history` (one delivery, revision cursor) return only your own deliveries in a scope you hold. Both are audited and read-only; there is no endpoint to create, retry, cancel or edit a delivery. No web screen is added by this increment.

## Running the worker (development/test only)

The worker is not part of the normal stack. With the restricted runtime credentials and a disposable or development database:

```sh
python -m app.notification_worker --once
```

One pass enqueues deliveries for newly delivered reminders, then handles at most 100 due deliveries, and prints counts only. A failed pass exits nonzero; a rolled-back claim never started a send. Stop the worker before a schema update or restore and keep it stopped after an older-backup restore until pending intent has been reviewed, as with the reminder and job consumers. The command-line worker uses the in-process synthetic channel; it cannot reach a provider.

## Data and engineering boundaries

Migration **0032_notification_delivery** adds `notification_deliveries` and `notification_delivery_events`. PostgreSQL guards (corrected by **0033_notification_integrity**) seal identity, one delivery per reminder cycle, creation only for a delivered reminder, attempt/revision progression, valid terminal timing, the channel allow-list and append-only history whose snapshots must contain exactly the expected fields, with the expected JSON types, and match the parent row on every one of them (identity, channel, state, revision, cycle, attempts, reason, next attempt, resolution and creation/update times). Deletes and truncates are denied. Runtime receives SELECT/INSERT/UPDATE on the current table and SELECT/INSERT on events; it still cannot read the general audit journal. Downgrade to 0031 drops all notification records and history; use it only on disposable data. Downgrade from 0033 to 0032 keeps the records, restores the older (less strict) history check and clears the `paused` reason on current rows, because the older constraint does not know it; sealed history keeps what happened.

Locks are always taken recipient user first, then delivery row. Disposable PostgreSQL testing exposed a deadlock when the finishing phase locked the row first; the finish and reconcile phases now follow the claim order, with a concurrent-worker test.

## What a real connector spike must prove

The synthetic channel defines the adapter contract: `send(key, recipient)` returning accepted, rejected, transient or timeout and idempotent on `key`, and `lookup(key)` returning delivered, absent or unavailable. A time-boxed spike with a throwaway account and invented content must show the real provider honours an idempotency key or exposes an equivalent lookup. If it does not, the path stays at-most-once with visible `unknown` states. Each spike needs its own approval, a stated data flow and no private records. This increment grants none.

No frontend, summaries, urgency levels, per-channel preferences, recurrence or production activation are supplied. CORE-11 remains partial.
