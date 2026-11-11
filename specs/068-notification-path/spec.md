# 068 — One notification path with a synthetic channel

Deliver the first item of the agreed synthetic-MVP order: a durable notification path for CORE-11 (and the delivery semantics reused by REM-01, ORG-03 and invoice filing). A *delivered* in-app reminder (spec 047) is handed to a **synthetic channel** with explicit delivery states, a stable recipient alias, quiet hours, day budgets, per-cycle deduplication, bounded retry and ambiguity reconciliation. No real provider, device push, email, address, secret or private data is introduced; a real connector needs its own time-boxed spike and separate authorization.

## Clarify / checklist

- One delivery per reminder cycle (`UNIQUE(reminder_id, cycle)`). Rescheduling a delivered reminder starts a new cycle and therefore a new delivery. Deliveries are created only for reminders in state `delivered`, enforced by a PostgreSQL trigger as well as the worker.
- States: `pending`, `delivered`, `failed`, `unknown`, `cancelled`. `delivered`/`failed`/`cancelled` are terminal and cannot be revived. `unknown` means the outcome of an attempt is not known and is resolved only by lookup.
- Recipient mapping stores an opaque alias derived from the owner ID (`synthetic:<24 hex>`); no name, address or device. Owner and scope must still be active and granted when each attempt is claimed.
- Quiet hours, the daily limit and pause reuse the owner's existing reminder preferences. The daily count is taken from sealed notification history (`delivered` and `reconciled` events) in the owner's local day. Deferral is recorded with a reason and next check time; it never discards a delivery.
- Bounded retry: at most 3 attempts, backoff 1/5/15 minutes after a transient error. A permanent rejection fails at once. After the final transient error the delivery fails with `attempts_exhausted`.
- Ambiguity: the attempt claim commits **before** the send. A timeout, an unexpected channel exception, or a claim older than 5 minutes (process died mid-send) becomes `unknown` and is reconciled by an idempotent lookup keyed by the delivery ID. Found → `delivered` (event `reconciled`); absent → one bounded retry; lookup unavailable → stay `unknown` and poll slowly. Nothing is resent blindly.
- Cancellation: a delivery is cancelled, with a reason, if the reminder is acknowledged/cancelled/rescheduled, the owner is inactive or the scope grant is gone.
- Privacy: no task title, detail or source text is copied into deliveries, events or audit. Owners read only their own deliveries and history in a granted scope (`POST /api/v1/notifications/query|history`, 25 per page, audited, no mutation endpoint).
- Restricted worker only (`python -m app.notification_worker --once|--loop`): development/test with restricted runtime credentials, bounded passes of at most 100, synthetic in-process channel, no provider connection, not started by default Compose. Locks follow one order everywhere: recipient user, then delivery row.

## Contract the synthetic channel proves (for later spikes)

`send(key, recipient) -> accepted | rejected | transient | timeout`, idempotent on `key`; `lookup(key) -> delivered | absent | unavailable`. A real connector spike must show the provider honours an idempotency key or exposes an equivalent lookup; otherwise the path is documented as at-most-once-with-visible-unknown rather than exactly-once.

## Out of scope

Real providers or accounts, device/OS push, email, per-channel preferences UI, frontend, daily summaries, urgency levels, recurrence, invoice filing and operations monitoring. CORE-11 stays partial; no counter claims full acceptance.

## Corrections after independent audit (PR following #24)

- **Paused scheduling.** A paused owner's due deliveries were returned to the due set unchanged on every pass, oldest first, so enough of them could fill the bounded pass and delay other owners. They are now parked once as `pending` with reason `paused` and excluded from selection until the owner resumes. Paused stays distinct from cancelled; quiet-hours, daily-limit and reconciliation behaviour are unchanged.
- **History integrity.** The 0032 history guard did not compare channel, next-attempt, resolution, creation or update times, nor require every field with the right JSON type. Migration 0033 makes it validate all fourteen snapshot fields against the parent delivery.
