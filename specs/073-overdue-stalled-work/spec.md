# Spec 073: Overdue and stalled work observation

**Status: specification frozen with owner decisions D1–D4 recorded (owner-approved 14 November 2026). Not implemented, not verified, not merged, not accepted. Owner approval of these decisions does not authorize implementation; implementation requires a separate explicit owner instruction.**

> **Merge record (added 14 November 2026, after the merge; the text above is retained as written at the time):** the frozen contract merged as [PR #36](https://github.com/LYF-FC/local-assistant-core/pull/36) (merge `2e04ff8`, 14 November 2026; push run 43611079243 passed) and the implementation, authorized separately by the owner on 14 November 2026, as [PR #37](https://github.com/LYF-FC/local-assistant-core/pull/37) (merge `4a7e624`, 14 November 2026). Pull-request-head CI passed on `2408a68` (run 43615751104) and the push to `main` at the merge commit `4a7e624` passed all six jobs (run 43624054196, attempt 1). Merging is integration only: it is not independent verification or owner acceptance, and no requirement, gate, count or priority changed because of it.

Baseline: `main` at `f617330f90e21c9af75cead7a8ea97d83580f7f0`. Worker, model, migration, operations, role and compose code are identical to `41aa5f3` (merge of PR #35); the only change between them is a test-only calendar fix.

This document assembles the design reviewed in the owner conversation of 14 November 2026: the initial draft, the predicate correction (worker selection preserved exactly), the clock-rollback and enqueue clarifications, the revised acceptance test 4b step 6, and the recorded owner decisions. It adds no requirement and changes no acceptance criterion, requirement scope, priority or gate status.

## 1. Specification

### 1.1 Requirement and gate mapping

| Item | Mapping | What this slice contributes | What stays open |
|---|---|---|---|
| **OPS-09** (register): "Infrastructure dashboard … jobs"; dependencies: "job health inventory; stale/failure semantics" | Partial | Queue-level overdue and stalled states for four durable queues | Service, NAS, storage, backup, certificate and model observation |
| **OPS-10** (register): "Periodic operational audit … overdue jobs" | Partial, second slice after spec 072 | An explicit, audited overdue-work observation | Capacity trends, periodic or scheduled reports, delivery, alerting |
| **PLATFORM-01**: "failure visibility" | Supporting | Eligible work that is not being taken becomes visible | Real handlers and real providers |
| **Gate 10** ([MVP acceptance](../../docs/MVP_ACCEPTANCE.md)): "Inspect … jobs status, overdue work" | Partial evidence toward one clause | Same | Disk headroom, backup age, last restore, reboot/restart verification, an independent observer |
| Gates 6, 11; MVP-05; DOC-X02; PLATFORM-02/03 | **Not touched** | None | Everything |

No acceptance criterion, requirement scope, gate status or priority changes.

### 1.2 Outcome

A technical administrator opens the Operations overview and clicks **Load work status**. They see one state for each observed queue, plus a fixed list of unobserved queues. Nothing loads with the overview, and nothing polls.

### 1.3 Observed queues

| Key | Source tables | Worker that makes the work eligible |
|---|---|---|
| `approved_jobs` | `job_outbox` | `jobs.claim()`, used by `app/worker.py` |
| `reminders` | `task_reminders` with `reminder_preferences` | `reminder_worker.candidates()` |
| `notifications` | `task_reminders` (enqueue step) and `notification_deliveries` with `reminder_preferences` | `notification_worker.enqueue_pass()` and `notification_worker.candidates()` |
| `filing` | `filing_executions` | `filing_worker.candidates()` |

**Not observed:** `calendar_sync`, `routines` and `work` are returned in a fixed `not_observed` list, never with a state. The UI labels them "Not observed by this view" and never "clear".

### 1.4 Eligibility, overdue and stalled semantics

#### Principles

- **P1. Worker selection stays selection-equivalent, with identical ordered candidate IDs.** Each worker's WHERE clause becomes a disjunction of shared eligibility functions, evaluated at the worker's own single `now` (one `identity.now_utc()` reading, as today). The joins, `ORDER BY`, `LIMIT`, locking (`FOR UPDATE`, `SKIP LOCKED`, `OF task_reminders`) and the `populate_existing` option stay unchanged. The shared functions take no grace parameter. Observer-only guards live solely in `operations.work_status`, and no worker module may import them.
- **P2. The observer evaluates the same functions at `c = now − G`,** using one app-clock reading.
- **P3. The observer adds guards only where it needs them.** Where a worker rule has an input with no time of its own (a preference flag, a policy revision, the absence of a delivery row), or a time column that can be written with a past value, the observer adds an eligible-since guard. The guard proves the row's eligibility inputs have not changed since `c`. These guards can make the observer *under-report* for at most `G` after a change; they can never affect a worker.
- **P4. No delay.** The grace period never delays a worker: workers still evaluate at `now`.

#### Constants

- `G = 120 s`, the observation grace period, **owner-approved (D2)**. It is a fixed engineering threshold, not configurable, and it applies only to the observer. Workers never use it.
- `LEASE = 60 s` (existing `jobs.LEASE`).
- `D = 5 min` (existing `IN_FLIGHT_DEADLINE`, shared by notifications and filing).

#### The eight shared eligibility functions

| # | Function | Predicate, exactly as in today's worker SQL with `now` replaced by `t` |
|---|---|---|
| E1 | `job_pending(t)` | `job_outbox.state = 'pending' AND available_at <= t` |
| E2 | `job_lease_expired(t)` | `job_outbox.state = 'leased' AND lease_until <= t` |
| E3 | `reminder_due(t)` | `r.state = 'scheduled' AND r.scheduled_at <= t AND (p.owner_id IS NULL OR p.enabled IS TRUE) AND (r.next_attempt_at <= t OR r.policy_revision <> coalesce(p.revision, 0))`, with `LEFT JOIN reminder_preferences p ON p.owner_id = r.owner_id` |
| E4 | `notification_enqueue_eligible()` | `r.state = 'delivered' AND d.id IS NULL`, with `LEFT JOIN notification_deliveries d ON d.reminder_id = r.id AND d.cycle = r.cycle`. It has **no time parameter**, because today's `enqueue_pass()` has none. |
| E5 | `notification_due(t)` | `(d.reason IS DISTINCT FROM 'paused' OR p.enabled IS DISTINCT FROM false) AND d.state IN ('pending', 'unknown') AND d.next_attempt_at <= t AND d.attempt_started_at IS NULL`, with `LEFT JOIN reminder_preferences p` |
| E6 | `notification_in_flight_expired(t)` | the same paused exclusion, `AND d.state = 'pending' AND d.attempt_started_at <= t − IN_FLIGHT_DEADLINE` |
| E7 | `filing_due(t)` | `f.state IN ('pending', 'unknown') AND f.next_attempt_at <= t AND f.attempt_started_at IS NULL` |
| E8 | `filing_in_flight_expired(t)` | `f.state = 'pending' AND f.attempt_started_at <= t − IN_FLIGHT_DEADLINE` |

#### How each worker uses them (selection unchanged)

| Worker | Current selection | After the refactor | Equivalence |
|---|---|---|---|
| `jobs.claim` | `(pending AND available_at <= now) OR (leased AND lease_until <= now)` | `E1(now) OR E2(now)` | Identical boolean expression |
| `reminder_worker.candidates` | the E3 expression with `now` | `E3(now)` | Identical. No `updated_at` term. |
| `notification_worker.enqueue_pass` | `state = 'delivered' AND d.id IS NULL` | `E4()` | Identical. No `delivered_at` term. |
| `notification_worker.candidates` | `P AND ((pending/unknown, next <= now, started IS NULL) OR (pending, started <= now − D))` | `E5(now) OR E6(now)` | `(P∧A)∨(P∧B) ≡ P∧(A∨B)`. Same join; `now` and `stale` come from one reading. |
| `filing_worker.candidates` | the E7 and E8 bodies joined by `OR` | `E7(now) OR E8(now)` | Identical |

**Claim-time rechecks are unchanged and consistent with the selection:**

- **Reminders:** `process` re-tests `scheduled_at > now`, `enabled`, and `policy_revision == revision AND next_attempt_at > now`.
- **Notifications and filing:** `claim` re-tests the in-flight deadline or `next_attempt_at` under row locks.

**Scrubbed filing rows:** `filing_worker.claim()` skips rows with `scrubbed_at` set, but `candidates()` never selects them. The `ck_filing_scrubbed` constraint allows `scrubbed_at` only in `filed`, `failed` or `cancelled`, so no divergence is possible.

#### Observer definitions

These use `c = now − G`. The observer-only guards are written in bold.

**`approved_jobs`**

- **overdue** = `E1(c)`.
- **stalled** = `E2(c)`: a lease that expired more than `G` ago and has not been reclaimed.
- **No extra guard needed:**
  - `available_at` is written only as the app clock at enqueue (`default=utcnow`) or as `now + 5·2^attempts` seconds on retry;
  - `lease_until` is written only as `claim time + 60 s`;
  - neither is ever written with a past value.
- **Clarification on exhausted attempts:**
  - `ck_outbox_attempts` caps attempts at 3, and `finish()` dead-letters a retry once attempts reach 3. So a *pending* row with exhausted attempts is reachable only through restore or manual writes.
  - The realistic case is a third lease that expired after a crash.
  - Either way, an overdue or stalled approved job with exhausted attempts **will be dead-lettered (`attempts_exhausted`) by `claim()`, not executed**.
  - A claimed job can also be dead-lettered by `finish()` as `authority_invalid` if `authorized()` no longer holds.
  - So "overdue" and "stalled" mean only "eligible to be claimed". They say nothing about whether the job will execute.

**`reminders`**

- **overdue** = `E3(c)` **AND `r.updated_at <= c` AND (`p.owner_id IS NULL` OR `p.updated_at <= c`)**.
- **Why the guard is observer-specific:**
  - E3 depends on preference inputs that carry no time: `enabled` and the revision mismatch.
  - `next_attempt_at` can be created with a past value: creation sets it from the scheduled time, so a reminder created or rescheduled for a past time is due immediately.
  - Every reminder write sets `r.updated_at`: creation sets it, and `task_reminders.change` sets `row.updated_at = recorded_now`.
  - Every preference write increments `revision` and sets `p.updated_at`, and the runtime role has no DELETE on preferences.
  - So when both timestamps are at or before `c`, the current inputs are exactly those that held at `c`, and `E3(c)` on the current row equals eligibility at `c`.
- **Without the guard:** a preference change or re-enable, or a newly created past-due reminder, would be reported overdue instantly.
- **Future-dated `updated_at`** (clock skew or restore): not overdue until the time passes. The worker is unaffected.
- **Absent preferences:** the guard reduces to `r.updated_at <= c`. Absent preferences combined with a non-zero `policy_revision` is unreachable through runtime writes (no DELETE grant); if it occurs, it is evaluated by the same rule.
- **stalled:** never. Reminder processing has no lease or in-flight marker.

**`notifications`**

- **overdue** = `[E4() AND r.delivered_at <= c]` OR `[E5(c) AND d.updated_at <= c AND (d.reason IS DISTINCT FROM 'paused' OR p.updated_at <= c)]`.
- **Enqueue eligibility and permission to send are separate stages.**
  - **Stage 1 (enqueue):** `notification_worker.enqueue_pass()` creates one delivery row for each delivered reminder cycle that has none (E4). It does not consult the owner's notification preferences. A delivered reminder of an owner whose preferences are disabled is still eligible for enqueue, and the worker creates its delivery.
  - **Stage 2 (delivery):** `notification_worker.claim()` decides whether a send is permitted. If the owner's preferences are disabled, it parks the delivery as `reason = 'paused'` without sending. It can also cancel the delivery (owner or scope unavailable, reminder closed), defer it (quiet hours, daily limit), or reconcile an `unknown` outcome. A send happens only after all of these pass.
  - The `notifications` queue can therefore report `overdue` because a delivered reminder is still waiting for **Stage 1**, even though that delivery will later be paused, deferred or cancelled and never sent. `overdue` on this queue means only that eligible queue work (enqueueing, delivery processing or reconciliation) has waited longer than the grace period. It never means a notification is pending send, will be sent, or should have been sent. After enqueue, a delivery parked as paused is excluded from `overdue` by the same paused exclusion the worker uses (E5 and E6).
- **The enqueue guard (`r.delivered_at <= c`), observer-only:**
  - E4 has no time input.
  - Eligibility to enqueue starts when the reminder enters `delivered`: `delivered_at` is set in the same change, and the check constraint requires it to be non-null in that state.
  - Eligibility ends when a delivery row for that cycle exists.
  - With a future-dated `delivered_at` the observer reports nothing, but the worker still enqueues the reminder (E4 is unchanged).
- **The due guard, observer-only:**
  - Park and `reconciled_absent` set `next_attempt_at = now`, and `d.updated_at` moves on every `notes.change`.
  - A paused row becomes eligible again when the owner re-enables preferences (a preference write), even though its `next_attempt_at` is the old park time. The `p.updated_at` term stops a just-resumed row from being reported.
  - A paused row with absent preferences is unreachable at runtime (parking requires disabled preferences, and preferences are not deleted). The NULL comparison means it is not reported.
- **What counts as overdue:**
  - **Unknown deliveries:** an `unknown` delivery whose reconciliation is due (`next_attempt_at <= c`) counts as overdue. Reconciliation looks the outcome up and never resends.
  - **Paused deliveries:** a parked delivery (`reason = 'paused'`) while the owner's preferences are disabled is excluded, exactly as the worker excludes it.
  - **Pending rows not yet parked:** a pending row whose owner just disabled preferences but which has not been parked yet *is* eligible, because the worker's due work is to park it. It is reported once that has gone untaken for `G`.
- **stalled** = `E6(c)`: `state = 'pending' AND attempt_started_at <= now − G − D`.
  - No extra guard: `attempt_started_at` is written only by `claim()` as the app clock, and every later write either resolves the row or clears the field.
  - The paused term is always true for in-flight rows, because `claim()` sets `reason = None`; it is kept only so E6 stays identical to the worker's rule.
  - The worker's response to such a row is to convert it to `unknown` and reconcile, never to resend.

**`filing`**

- **overdue** = `E7(c)` **AND `f.updated_at <= c`**.
  - Same reasoning as notifications: `reconciled_absent` sets `next_attempt_at = now`, and `filing.change` sets `updated_at`.
  - It includes `unknown` executions whose reconciliation is due. It has no paused or enqueue part.
- **stalled** = `E8(c)`: `state = 'pending' AND attempt_started_at <= now − G − D`, converted to `unknown` and reconciled, never re-applied.

**Queue state:** `stalled` if any stalled rule holds, otherwise `overdue` if any overdue rule holds, otherwise `none_observed`. `stalled` takes precedence so the response stays a single value.

**Wording rules, enforced in the copy:**

- `none_observed` means "no eligible work older than the grace period was observed". It does not mean a worker is running, healthy or able to process anything: a worker can be down with nothing due.
- `overdue` and `stalled` mean eligible work is not being taken. That is consistent with a stopped, undeployed, blocked or failing worker, and the view does not say which.
- Neither state describes worker health or liveness.

#### Default stack behaviour (owner-accepted, D4)

- On the baseline, `infra/core/compose.yml` defines worker services only for reminders (`reminders` profile), routines and calendar. The notification and filing workers and the approved-jobs worker have no compose service and run only as one-shot development/test commands.
- In the default Compose stack, the `approved_jobs`, `notifications` and `filing` queues can therefore show `overdue` (or `stalled`) whenever they hold eligible work. That is the truthful observation and the copy must not soften it.
- The UI states, for every queue, that the view is not a worker-health check: it does not say whether a worker is deployed, running or healthy.

### 1.4.1 Clock assumption and rollback limitation

**Clock assumption.** The observer's grace-period reading assumes a **non-decreasing application clock**. Workers, the write paths and the observer all use the application wall clock (`identity.now_utc()`):

- `r.updated_at` (`task_reminders.change` and creation);
- `p.updated_at` (preference writes);
- `d.updated_at` (`notes.change`) and `f.updated_at` (`filing.change`);
- `r.delivered_at` (reminder delivery);
- the values those paths write into `available_at`, `next_attempt_at`, `lease_until` and `attempt_started_at`.

The observer-only guards (`r.updated_at <= c`, `p.updated_at <= c`, `d.updated_at <= c`, `f.updated_at <= c`, `r.delivered_at <= c`) and the guard-free rules for E1, E2, E6 and E8 treat a timestamp at or before `c = now − G` as evidence that the eligibility already existed at `c`. That inference holds only while the clock does not move backwards.

**Limitation: rollback can cause premature reports.** If the application clock steps backwards, through manual correction, NTP stepping, host or VM restore, or container migration, a write made *after* the cutoff can receive a timestamp at or before the cutoff. The affected row can then be reported `overdue` or `stalled` before it has actually been eligible and untaken for `G`. A forward clock step has the opposite effect: rows are reported later, or a future-dated timestamp is not reported until the clock passes it.

**No exact measurement across rollback.** The observer does not guarantee exact grace-period measurement across a clock rollback, and the view's states are not evidence of how long work has waited. This slice introduces no monotonic clock, database-clock substitution, sequence or other new clock mechanism.

**Workers are unaffected.** Clock behaviour changes only what the observer reports. Worker eligibility (E1–E8 at the worker's own `now`) and worker execution are the same as today, rollback included.

### 1.5 API

**`POST /api/v1/operations/work-status`**

- Strict body `{"scope": "technical_admin"}`; extra keys are forbidden and inputs are hidden from validation errors.

**`200` response.** It has exactly these keys and nothing else:

```json
{
  "schema_version": 1,
  "scope": "technical_admin",
  "actor_id": "<caller uuid>",
  "checked_at": "<UTC>",
  "valid_until": "<checked_at + 60 s>",
  "queues": [
    {"key": "approved_jobs", "state": "none_observed|overdue|stalled"},
    {"key": "reminders", "state": "none_observed|overdue"},
    {"key": "notifications", "state": "none_observed|overdue|stalled"},
    {"key": "filing", "state": "none_observed|overdue|stalled"}
  ],
  "not_observed": ["calendar_sync", "routines", "work"],
  "excludes": ["counts", "ages", "owners_and_scopes", "items", "worker_liveness", "capacity", "backups", "restore"]
}
```

`queues` is in the fixed order shown, and the `reminders` state can never be `stalled`.

**Never returned:**

- counts, age bands or per-item timestamps;
- owner, scope or member breakdowns;
- item ids, payloads, recipients or destinations;
- reasons, attempts or the grace value in effect.

Adding any of these needs a separate owner decision.

**Disclosure statement (in the spec and the UI text).** Even queue-level aggregates over all members' reminders, notifications, filing and approved jobs are sensitive operational metadata about other members' private activity. The output is therefore limited to one state per queue.

### 1.6 Authorization, privacy and audit

**Authority.** The same `authority(db, token, csrf, "technical_admin", event_prefix="operations", scope_lock="installation")` path as `operations.read` and `audit_summary`:

- HTTPS and exact Host/Origin;
- current session and CSRF;
- current grant and the installation membership lock;
- session revalidation after the queries;
- the 60-second receipt check after the query (the same pattern as `operations.read`).

**Grants.** None added and no `SECURITY DEFINER` function, because none is needed:

- `butler_runtime` already holds SELECT on `job_outbox`, `task_reminders`, `reminder_preferences`, `notification_deliveries` and `filing_executions`;
- the queries are existence checks over existing indexes (`ix_outbox_ready`, `ix_reminder_due`, `ix_notification_due`, `ix_filing_due`);
- the runtime role keeps USAGE on `public` only: no `work` schema access and no SELECT on `audit_events`.

**Consistency with policy.**

- *Current policy:* [ARCHITECTURE.md](../../ARCHITECTURE.md) states "Technical administration does not imply content access". Spec 066 limits job data to the caller's own jobs, and spec 072 counts no content-domain events.
- *What this view adds:* no content, but a new class of disclosure. It derives household-wide state from other members' private reminder, notification, filing and approved-job records.
- *Decision:* the owner has **accepted** this derived disclosure (D1, 14 November 2026), on the boundary below. That acceptance covers only this view and this boundary; it does not widen technical-administration access elsewhere.

**Accepted residual privacy risk (D1).**

- *Probing:* a technical administrator who reloads repeatedly while a worker is stopped can see a queue change to `overdue` (or `stalled`). This applies to all four observed queues: approved jobs, reminders, notifications and filing. It reveals, to roughly the grace period's precision, approximately when another household member's private work in that queue became due.
- *Small households:* in a small household, for example one of two members, it may reveal whose work it was.
- *Mitigation, partial:* every load writes one metadata-only `operations.work_status` audit event, which deters and records probing but does not prevent it.
- *Clock rollback:* reports may be premature after the application clock steps backwards (§1.4.1). Real-host clock behaviour is not verified by this slice.
- *Status:* the owner has accepted this risk as stated. No throttle or extra control is part of this design.

**Disclosure boundary (D1, fixed).** Queue-level states only: `none_observed`, `overdue`, `stalled`, plus the fixed `not_observed` list. Excluded:

- counts, age bands or per-item timestamps;
- owner, member or scope breakdowns;
- item ids, payloads, recipients or destinations;
- reasons, attempt counts, or the grace value in effect.

Any further detail needs a new, separate owner decision.

**Audit-before-response.**

- Exactly one `operations.work_status` event, with outcome `success` and `metadata: {}`, is written and committed with the request before the response is released.
- No queue state goes into the audit metadata, so no cross-member signal is persisted.
- If the audit write fails, the whole response is withheld: no payload and no audit row.

### 1.7 Failure, stale data and unavailability

**No partial response.**

- Any database error, `lock_timeout` (2 s), `statement_timeout` (5 s), revalidation failure or audit failure rolls back the transaction.
- The route returns sanitized 503 or 401 through the existing `execute` wrapper.
- A failure is never reported as a queue state, and never as `none_observed`.

**Freshness.** `checked_at` is the app-clock check time, `valid_until` is 60 seconds later, and the client discards the response after that.

**Non-PostgreSQL databases.** The queries are portable ORM existence checks, so SQLite development returns real states, as `operations.read` does. The timeouts apply on PostgreSQL only.

### 1.8 UI

A new **Work status** section inside the Operations overview, with its own region label and its own status element. It must not repeat the spec 072 locator ambiguity.

**Loading and parsing:**

- An explicit **Load work status** button.
- A strict parser: exact keys, fixed queue order, a closed state set (`reminders` cannot be `stalled`), the exact `not_observed` and `excludes` lists, the caller as actor, and `valid_until = checked_at + 60 s`.

**Clearing:**

- clears at 60 seconds, when the tab is hidden, on session, grant or membership change, and on failure;
- discards late or superseded responses using a generation guard and abort;
- no browser storage, URL state or download.

**Copy:**

- `overdue`, generic (approved jobs, reminders, filing): "Eligible work has waited longer than the grace period. This does not show why, or what the outcome will be."
- `overdue`, **notifications**: "Notification queue work (queuing, processing or reconciling a delivery) has waited longer than the grace period. This does not mean a notification will be sent: a queued delivery may still be paused, deferred or cancelled."
- The section must not describe notification `overdue` with words such as "unsent", "pending send", "missed notification" or "will be delivered".
- `stalled`: "An attempt or lease expired and was not taken over."
- `none_observed`: "No overdue or stalled work was observed. This is not a worker health check."
- The unobserved queues are listed as not observed.
- For every queue, the section states that the view is not a worker-health check (D4).

### 1.9 Explicitly not delivered

- worker heartbeat, liveness or health claims;
- capacity or disk monitoring;
- backup freshness or restore readiness;
- an independent observer, alerting or notification of the administrator;
- scheduled or periodic reports;
- retry, requeue, cancel or any other control;
- per-item, per-owner or per-scope views;
- counts, ages or reasons;
- the calendar, routine or Work queues;
- real-host restart verification, or RPO/RTO claims;
- exact grace-period measurement across application-clock rollback or forward steps; any clock-monotonicity mechanism;
- any capability beyond D1–D4 as approved. Owner approval does not authorize implementation or acceptance.

The spec 038 recovery-assessment CLI remains the tool for restored databases.

## 2. Files and code paths for a later implementation

This list describes where a later implementation would change code. It is not an implementation task list and does not authorize implementation.

**Backend: shared eligibility and the observation**

- `backend/app/queue_eligibility.py` (new) holds the parameterized rules E1–E8 of §1.4.
- `backend/app/jobs.py` `claim()`: use E1 and E2 with `as_of = now`. Ordering, `skip_locked`, limit and dead-lettering stay unchanged.
- `backend/app/reminder_worker.py` `candidates()`: use `E3(now)`.
- `backend/app/notification_worker.py` `enqueue_pass()` and `candidates()`: use `E4()`, and `E5(now) OR E6(now)`.
- `backend/app/filing_worker.py` `candidates()`: use `E7(now) OR E8(now)`.
- `backend/app/operations.py`:
  - new constants `WORK_QUEUES`, `WORK_STATES`, `WORK_NOT_OBSERVED`, `WORK_EXCLUDES` and `WORK_GRACE = timedelta(seconds=120)`;
  - module-level timeout constants, so tests can lower them;
  - a `WorkStatusRead` model and `work_status(db, token, csrf, body)`: authority, then `SET LOCAL` timeouts, then the existence queries at `now − WORK_GRACE` with the observer-only guards, then revalidation and the receipt check, then the audit, then a `Result`.
- `backend/app/operations_routes.py`: `POST /work-status` through `execute(...)`.

**Backend: migration and its knock-on changes (see §3)**

- `backend/alembic/versions/0038_work_status_audit_category.py` (new).
- `backend/tests/test_calendar_schema.py` and `scripts/test-db-restore.sh`: migration head becomes `0038_work_status_audit_category`.

**Backend tests**

- `backend/tests/test_operations_work_status.py`: SQLite unit tests.
- `backend/tests/test_queue_eligibility.py`: rule unit tests.
- `backend/tests/integration/test_work_status_postgres.py`: new.
- `backend/tests/integration/test_queue_eligibility_postgres.py`: worker equivalence and no-delay tests.
- `backend/tests/integration/test_audit_summary_postgres.py`: add one `CASES` row; extend the round trip.

**Frontend**

- `frontend/src/operations-api.ts`: `workQueues`, `workStates`, `workNotObserved`, `workExcludes`, `parseWorkStatus`, `readWorkStatus`.
- `frontend/src/WorkStatusSection.tsx` (new).
- `frontend/src/OperationsPanel.tsx`: render the section.
- `frontend/src/operations-api.test.ts`: parser tests.
- `frontend/test-harness/work-status.html` and `.tsx`, plus `frontend/browser/work-status.spec.ts`: mocked component tests.
- `frontend/e2e/calendars.spec.ts`, operations group: real-stack tests with region-scoped locators.

**Documentation, with a later implementation**

- `specs/073-overdue-stalled-work/{tasks,convergence}.md`.
- `docs/OPERATIONS_OVERVIEW.md`: an "unknown" list update and a new section.
- Register notes for OPS-09/OPS-10, the Gate 10 entry in `PROJECT_MASTER.md` and the `ARCHITECTURE.md` operations line, then regenerate the derived views.

## 3. Audit taxonomy

**Current mapping (verified in `0037_audit_summary.py` on the baseline).**

- `operations.read` and `operations.audit_summary` map to `operations_read`.
- `operations.session_denied` maps to `denied_access`.
- Every other `operations.*` event falls through to `ELSE 'other_security'`, so without a change `operations.work_status` would be counted as `other_security`.
- The spec 072 tests pin this behaviour with `("operations.brand_new_event", "success", "other_security", "success")`.

**Why `other_security` would be wrong.** Spec 072 defines `other_security` as the holding category for auth or operations events that have not been reviewed: "a new event type lands in an `other_*` category until reviewed". `operations.work_status` *is* reviewed, by this specification, and it is a successful technical-administrator view of operations, which is exactly what `operations_read` ("Operations views") means.

**Options considered:**

- **(a) Accept `other_security`.** Rejected: semantically incorrect, as above.
- **(b) Reuse `operations.read`, with a metadata discriminator such as `{"view": "work_status"}`.** No migration needed, but rejected. It overloads an existing event type with a different read, changes `operations.read`'s metadata contract, and makes the audit trail rely on metadata the summary deliberately ignores.
- **(c) Add one literal to the reviewed mapping.**

**Decision (D3, owner-approved, 14 November 2026): migration `0038_work_status_audit_category`.** `operations.work_status` is classified as `operations_read`.

**Upgrade:** `CREATE OR REPLACE FUNCTION public.butler_audit_summary(p_token text, p_end timestamptz, p_hours integer)`.

- The body is identical to 0037 except one line: `WHEN a.event_type IN ('operations.read', 'operations.audit_summary', 'operations.work_status') THEN 'operations_read'`.
- It restates `LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog`.
- Unchanged: the token binding, the recent-window predicate (60 s before / 5 s after `clock_timestamp()`), the 24/168-hour guard and the `auth.`/`admin.`/`operations.` family filter.
- The signature and return type are the same, so the owner, the runtime EXECUTE grant and the PUBLIC revocation are kept. `REVOKE ALL … FROM PUBLIC` is re-run defensively, and `runtime_role.configure` needs no change.

**Downgrade:** `CREATE OR REPLACE` back to 0037's exact body. No `DROP`; 0037's downgrade still drops the function. No data changes: existing `operations.work_status` rows count as `other_security` again after a downgrade.

**Compatibility:**

- The seven category keys, their order and the response shape are unchanged.
- The strict frontend parser (`auditCategories`) and `operations.AUDIT_CATEGORIES` are unchanged.
- All existing spec 072 `CASES` still hold, including `operations.brand_new_event` → `other_security`.

**Required tests:**

- the new case `operations.work_status` → `operations_read`;
- the `0038 ↔ 0037` round trip (`0038 → 0037` maps `work_status` to `other_security`; `0037 → 0038` maps it back), with the existing `0036` round trip passing through both;
- the guard and privilege checks (`SECURITY DEFINER`, `proconfig = ['search_path=pg_catalog']`, owner, no PUBLIC execute, runtime execute, single signature, actor binding, recent window);
- migration-head assertions moved to `0038`.

**Ordering:** the migration ships in the same change as the route, so no `operations.work_status` event ever exists unclassified on `main`.

## 4. Owner decision record

**Approval date:** 14 November 2026.

**Scope of approval:** these decisions approve the design documented in this specification as it stands. They do not expand its scope, they are not implementation authorization, and they are not implementation acceptance, verification, or acceptance of OPS-09, OPS-10, PLATFORM-01 or any MVP gate.

| ID | Decision | Owner outcome | Accepted limitations |
|---|---|---|---|
| D1 | Household-wide derived disclosure to technical administrators | **Approved** | Queue-level states only (§1.5 and §1.6). Accepted residual risk: repeated reloads can reveal approximately when, and in small households possibly whose, private item became due. Audit records but does not prevent probing. No counts, ages, owners, scopes, records, ids or per-item details. |
| D2 | Observation grace period | **Approved: fixed 120 s** | Observer only; workers are never delayed. Measurement assumes a non-decreasing application clock; rollback can cause premature reports (§1.4.1). |
| D3 | Audit taxonomy | **Approved: migration 0038** | `operations.work_status` → `operations_read`. The seven-category response shape and taxonomy are otherwise unchanged (§3). |
| D4 | Default Compose behaviour | **Approved** | `approved_jobs`, `notifications` and `filing` may show `overdue` in the default stack because their workers are not deployed there. The UI must state that the view is not a worker-health check. |

No other owner decision is recorded or implied. In particular, the following remain undecided:

- implementation authorization;
- any additional disclosure detail;
- any throttle;
- any new clock mechanism;
- observation of other queues;
- any change to requirement scope, priority or gate status.

The decisions are also recorded in [DECISIONS.md](../../DECISIONS.md) and reflected in the Gate 10 entry of [PROJECT_MASTER.md](../../PROJECT_MASTER.md).

## 5. Acceptance tests for a later implementation

These tests define what a later implementation must demonstrate. None has been written or run.

### Restricted-runtime-role PostgreSQL tests: observer semantics (`test_work_status_postgres.py`)

1. **Approved jobs:**
   - pending at `available_at = now − G − 1 s` is overdue; at `now − G + 5 s` it is not;
   - leased with `lease_until = now − G − 1 s` is stalled; with `now − G + 5 s` it is not;
   - a fresh lease is `none_observed`;
   - a stalled row with `attempts = 3` is reported stalled, and one subsequent `claim()` dead-letters it (`attempts_exhausted`) without executing it;
   - a claimed job whose approval has since been revoked is dead-lettered by `finish()` as `authority_invalid`.
2. **Reminders:**
   - due at the cutoff boundary (both sides), with `r.updated_at` and `p.updated_at` older than `c`;
   - not overdue when `next_attempt_at` is in the future (quiet-hours deferral), when preferences are disabled, or when `scheduled_at` is in the future;
   - a revision mismatch is overdue only once `p.updated_at <= c`;
   - **future-dated `p.updated_at`**: not overdue, yet one worker pass still selects and processes the row;
   - **future-dated `r.updated_at`**, and a reminder created now with a past `scheduled_at`: not overdue, yet the worker selects it;
   - **absent preferences**: `policy_revision = 0` is overdue by the time branch with `r.updated_at <= c`; a non-zero `policy_revision` follows the same rule;
   - the state is never `stalled`.
3. **Notifications:**
   - an enqueue-eligible reminder with `delivered_at <= c` is overdue;
   - **future-dated `delivered_at`**: not overdue, yet `enqueue_pass()` still creates the delivery;
   - pending or `unknown` at the boundary is overdue only with `d.updated_at <= c`;
   - an `unknown` delivery whose reconciliation is due is overdue;
   - a parked paused delivery with disabled preferences is excluded;
   - a resumed paused delivery is not overdue until `p.updated_at <= c`, but the worker selects it immediately;
   - a pending row of a just-disabled owner, not yet parked, is overdue after `G` (the worker would park it);
   - stalled at `attempt_started_at = now − G − D − 1 s`, not stalled at `now − G − D + 5 s`; one worker pass converts a stalled row to `unknown` and never resends.
4. **Filing:** the same boundary and `updated_at` cases as notifications (without the enqueue and paused cases), with stalled rows converted to `unknown` and never re-applied. A scrubbed row in `pending` state is rejected by `ck_filing_scrubbed`, confirming it can never be selected.

4a. **Clock rollback shows premature reporting (limitation test).** Restricted runtime role, synthetic data, patched `identity.now_utc()`:

1. Set the application clock to `T0`. The observer cutoff is `c = T0 − G`.
2. Step the application clock **backwards** to `T0 − G − 10 s`.
3. Through the real application write path, create a scheduled reminder whose `scheduled_at` is in the past, with preferences enabled and unchanged since before `c`. The new row gets `r.updated_at = T0 − G − 10 s`, which is at or before `c`, although it was written after the observation cutoff.
4. Restore the clock to `T0` and call the observer. **Assert that `reminders` is reported `overdue`**, even though the row has existed for only a few seconds of real time. This records the documented limitation.
5. **Assert the workers are unaffected:** one reminder worker pass at `T0` selects and processes the row exactly as the pre-refactor selection statement would.

The test is named and documented as a demonstration of the limitation, not of correct behaviour. It does not establish real-host clock behaviour.

4b. **Enqueue is eligible regardless of preferences, and permission to send is decided later.** Restricted runtime role, synthetic channel:

1. An owner has `reminder_preferences.enabled = false`, `p.updated_at <= c`, and a reminder in `delivered` state with `delivered_at <= c` and no delivery for its cycle.
2. **Assert the observer reports `notifications` as `overdue`** (enqueue branch).
3. Run `enqueue_pass()`. **Assert one `pending` delivery is created** with `next_attempt_at = now`, matching the frozen pre-refactor `enqueue_pass` selection.
4. Run one notification candidates and claim pass. **Assert the delivery is parked** (`reason = 'paused'`, state `pending`), and that the synthetic channel recorded **no send**.
5. **Assert the observer now reports `none_observed`** for that delivery (paused exclusion).
6. **Re-enabling preferences: the worker selects immediately; the observer reports only when both timestamp guards hold.**

   The notification `overdue` rule for this row is: `E5(c)`, plus the observer-only guards `d.updated_at <= c` and (because `reason = 'paused'`) `p.updated_at <= c`.

   The application clock is patched and only ever moves forward in this step. The observer runs as the restricted runtime role at each controlled `now`, with `c = now − G`. The worker check at each point uses `notification_worker.candidates()` only (selection, with no claim or process), so the delivery row is never changed by the worker during this step.

   **Starting point (from steps 1–5).** The delivery is `pending` with `reason = 'paused'`, and it was parked at `T_p`, so `d.next_attempt_at = d.updated_at = T_p`. Preferences are disabled.

   **6.1 Enable through the real write path.** At application time `T_e = T_p + 2G`, set `enabled = true` through the real preferences endpoint (expected-revision write). Assert `p.updated_at = T_e` and that the revision was incremented.

   **6.2 The worker selects immediately.** At `now = T_e`, assert that `candidates()` returns the delivery. Its eligibility is unchanged from the pre-refactor selection: `next_attempt_at <= now`, `attempt_started_at IS NULL`, and the paused exclusion no longer applies because preferences are enabled. This happens without waiting for the grace period. Assert that the observer does **not** report `notifications` as `overdue`.

   **6.3 Only the `p.updated_at` guard blocks.** At `now₁ = T_e + G/2`, so `c₁ = T_e − G/2`: `d.updated_at = T_p <= c₁` and `next_attempt_at = T_p <= c₁` (E5 and the `d` guard hold), but `p.updated_at = T_e > c₁`. Assert the observer does **not** report `overdue`, and `candidates()` at `now₁` still returns the delivery.

   **6.4 Only the `d.updated_at` guard blocks.**
   - Advance to `now₂ = T_e + 2G`.
   - **Fixture arrangement:** in a separate database-owner connection, set only `d.updated_at = now₂`. State, `reason`, `next_attempt_at`, `attempt_started_at`, `revision` and the event history stay unchanged. Bypass the delivery seal trigger for that single fixture statement only if it rejects the write.
   - With `c₂ = T_e + G`: `p.updated_at = T_e <= c₂`, `next_attempt_at = T_p <= c₂` (E5 holds), but `d.updated_at = now₂ > c₂`. Assert the observer does **not** report `overdue`.
   - Assert that `candidates()` at `now₂` still returns the delivery, which shows the arrangement did not change worker selection. Worker eligibility does not read `updated_at`.

   This arrangement is needed because, on a parked delivery, the real write paths always give `next_attempt_at = updated_at`. The test therefore isolates a guard that is defensive under current write paths, and it is labelled as a fixture arrangement, not a reachable runtime sequence.

   **6.5 Both guards hold.** At `now₃ = T_e + 3G + 1 s`, so `c₃ = T_e + 2G + 1 s`: `p.updated_at <= c₃`, `d.updated_at <= c₃` and `next_attempt_at <= c₃`. Assert the observer now reports `notifications` as `overdue`, and that `candidates()` still returns the delivery.

   **6.6 No side effects.** Assert the delivery row's state, revision and events are unchanged by steps 6.2 to 6.5, apart from the step 6.4 fixture column. Assert that the synthetic channel recorded no send throughout, and that exactly one metadata-only `operations.work_status` audit event was written for each observer call.

   Also assert that the notifications `overdue` explanation returned to the UI layer (through the mocked component test) uses the notifications-specific text from §1.8.

### Restricted-runtime-role PostgreSQL tests: output, privacy, authorization and failure

5. **Precedence and output:**
   - a stalled row together with an overdue row gives `stalled`;
   - the response has exact keys and order, and contains no counts, ids, timestamps or scopes;
   - `not_observed` is exactly `["calendar_sync", "routines", "work"]`, with no state attached.
6. **Permutation:** moving the same rows between owners and scopes gives a byte-identical `queues` array.
7. **Protected data:** as `butler_runtime`, `has_schema_privilege('work', 'USAGE')` is false and selecting from `work.*` or `audit_events` raises a permission error. A statement-capture listener on the request shows only the allowed tables are read: the identity and lock tables, the five queue tables, and an INSERT into `audit_events`.
8. **Authorization:** non-administrator, revoked grant, expired or idle session, missing CSRF, wrong Origin and extra body keys each get a denial with no payload.
9. **Audit failure:** an induced failure of the audit insert gives 503, no payload and no `operations.work_status` row.
10. **Timeouts:**
    - a competing `ACCESS EXCLUSIVE` lock on `task_reminders` gives 503 after the 2-second lock timeout, with no audit row;
    - a statement-timeout constant lowered in the test gives 503, with no audit row;
    - in neither case is any state returned.
11. **Successful audit:** exactly one `operations.work_status` row with `metadata = {}`, committed before the response.

### Worker equivalence and no delay (`test_queue_eligibility_postgres.py`)

12. **Same selection as before.** Frozen copies of the five pre-refactor selection statements live in the test module: `jobs.claim`, the reminder candidates, `enqueue_pass`, the notification candidates and the filing candidates. They run against one fixture matrix, with `now_utc` patched to a fixed `T`. The refactored worker functions must return **identical ordered id lists** for `limit` values of 1, 2 and 100 (for `jobs.claim`, the same single claimed row each time). The matrix covers:
    - every branch and both sides of every boundary;
    - future-dated `p.updated_at`, `r.updated_at` and `delivered_at`;
    - absent preferences, paused with preferences enabled and disabled;
    - `unknown` rows, in-flight rows at `D` ± 1 s;
    - exhausted attempts and an expired lease;
    - a scrubbed terminal filing row.
13. **Structural guarantee:**
    - the shared functions take only `t` and have no grace parameter;
    - worker modules import none of the observer guards (checked statically);
    - each worker's statement keeps its join, order, limit and lock options (the compiled statement options are compared in the test).
14. **Grace never delays workers:**
    - rows that became eligible exactly at `T` and at `T − 1 s` are selected and processed by one pass of each worker at `T`;
    - at that same `T` the observer reports `none_observed` for them;
    - after the pass the rows are claimed or resolved;
    - repeated with `G` set to 10 minutes: worker results are identical.
15. **Same rules at the same time:** at a frozen `t`, `E*(t)` selects exactly the rows each worker selects with `now_utc` patched to `t`. This proves one rule; results at different times are not expected to match.
16. **Synthetic process test:**
    - with the worker stopped, a due notification is `overdue`; after one real `notification_worker --once` subprocess pass it is `none_observed`;
    - a row whose attempt started `D + G` ago is `stalled`, and one pass converts it to `unknown`.

    This is synthetic-channel evidence only, not real-host behaviour.
17. **Existing suites unchanged:** the existing reminder, notification, filing and job worker test suites and the Batch 4 restart tests pass unmodified.

### Audit taxonomy

18. The `CASES` row for `operations.work_status` maps to `operations_read`, and all existing `CASES` still hold.
19. The `0038 ↔ 0037` round trip and the guard and privilege checks pass, and the migration-head assertions are updated.

### Backend unit and frontend tests

20. **SQLite API tests:** a strict request, authority denials, and correct states on SQLite. An invalid body is rejected without echoing its input.
21. **Parser unit tests (mocked):** reject wrong keys, wrong order, unknown states, a `stalled` reminders queue, a foreign actor, a wrong validity time, any count or id field, and any change to `not_observed` or `excludes`.
22. **Mocked component tests** (`browser/work-status.spec.ts`; mocked API, local opt-in, not hosted CI evidence):
    - nothing loads before or after the explicit click, and nothing polls;
    - clears when the tab is hidden, and at 60 seconds;
    - late responses are discarded after hiding, after expiry and after a newer request;
    - a 503 shows sanitized "unavailable" with no states, and an explicit retry works;
    - an invalid payload shows nothing, and a 401 signs out once;
    - no storage is written;
    - the notifications `overdue` copy is the exact §1.8 text, and none of the prohibited phrases appear.
23. **Real-stack Playwright** (`e2e/calendars.spec.ts` in the hosted `containers` job): a technical administrator loads the section and gets a 200 with `no-store`, the exact keys, states from the allowed set, and the unobserved queues labelled as not observed. A hidden tab clears it. A finance-only member gets no section and a server denial. Locators are scoped to the Work status region. The notifications `overdue` copy is the exact §1.8 text, and none of the prohibited phrases appear. The expiry and late-response cases are covered only by test 22.

### Hosted CI

24. All six jobs pass on the PR head, and the run is recorded in the PR metadata. None of this evidence establishes real-host behaviour, verification or acceptance.
