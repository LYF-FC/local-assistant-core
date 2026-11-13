# Batch 3: commit 3 audit record (F1 and database integrity)

Status: recorded at commit 3 of `codex/batch3-calendar-recurrence`. It documents what migration
`0035_calendar_provider_sync` enforces in the database, the decision on audit item F1 of
`BATCH3_CALENDAR_RECURRENCE_PROPOSAL.md` section 6.3, and what it deliberately does not prove.
Everything below is exercised by `backend/tests/integration/test_calendar_provider_schema_postgres.py`
against a disposable PostgreSQL 16 database as the restricted `butler_runtime` role.

## F1 decision: database enforcement

**Invariant.** For an override row, `deleted_by_cascade` is true only while `state = 'deleted'`,
and the pair (`sequence`, `deleted_by_cascade`) changes only in these ways:

| Transition | `sequence` | `deleted_by_cascade` | `deleted_at` | Other conditions |
|---|---|---|---|---|
| insert | any | false | set iff `deleted` | `revision = 1`; series not forgotten; `active` only under an `active` series |
| `active` to `deleted` (cascade) | unchanged (the last upsert) | becomes true | set | the series reads `deleted` in the same transaction |
| `active` to `deleted` (explicit delete) | strictly higher | false | set | |
| `deleted` to `deleted` (floor raise) | strictly higher | false (a true flag becomes false) | unchanged | |
| `deleted` to `active` (revive) | strictly higher | false | NULL | series `active`; 100 active limit |
| `active` to `active` (upsert) | strictly higher | false | NULL | |
| any to `forgotten` | unchanged | false | NULL | source reads `forgotten` |

Everything else is refused: lowering or keeping the floor, keeping the flag true across any
change, setting the flag on an insert, on an active row, on a delete-origin tombstone, with a
changed floor, or while the series is still active, and every update of a forgotten row. Series
follow the same strictly increasing floor, preserved `deleted_at` on a floor raise, and terminal
`forgotten` state (they have no origin flag).

**Mechanism.** `butler_calendar_override_guard` (BEFORE INSERT OR UPDATE), the CHECK constraints
`ck_calendar_override_cascade`, `_deleted_at`, `_content`, and the deferred constraint trigger
`butler_calendar_series_orphans` (an active override cannot outlive a non-active series at commit).

**Required write order (consequence for commit 4).** The series is written to `deleted` first, then
its active overrides are cascaded, in one transaction. Writing an override cascade before the series
delete is refused by the guard (`butler_calendar_override_floor_origin`). A page whose net result
revives a series that it also deleted writes: series to `deleted`, cascade, series to `active`.

## Mutation paths audited

| Path | Guard |
|---|---|
| Application: series delete with cascade | series update, then override updates, one transaction |
| Application: override upsert, delete, revive, floor raise, resend | override guard |
| Application: series revive | series guard; overrides stay `deleted` |
| Forgetting | source forgotten first, then scrub; deferred trigger refuses an incomplete scrub |
| Direct SQL by `butler_runtime` | the same triggers; no DELETE or TRUNCATE grant |
| Direct SQL by the table owner | the same triggers; DELETE and TRUNCATE refused by seal triggers |
| `calendar_sources` updates | existing sealed guard plus the exclusivity trigger |

## Concurrency and transaction boundaries

* Every guard takes `SELECT ... FOR UPDATE` on the `calendar_sources` row first, then reads the
  series row. Writers therefore serialize per source and always read committed series state
  (READ COMMITTED).
* The application protocol already locks the source first (owner, source, sync state), so there is
  no lock-order inversion. A direct-SQL writer that updates an override row before taking the source
  lock can deadlock against a protocol writer; PostgreSQL aborts one transaction (SQLSTATE 40P01).
  This is fail-safe: no invalid state is committed. Tested in
  `test_cascade_and_explicit_override_writes_never_leave_an_invalid_state` (accepts either outcome and
  asserts the invariant on the committed row).
* `calendar_changes.seq` is gapless by the insert guard under the source lock, and
  `butler_calendar_change_counter` (deferred) requires `applied_seq = max(seq)` at commit. Change
  rows must be inserted before the `applied_seq` update inside one transaction.

* The deferred orphan check (`butler_calendar_series_orphans`) is evaluated at commit against the
  series' **current** state. A page whose net result revives a series that it also deleted writes
  `deleted`, the cascade, then `active` (and may resend an override above its floor); the queued
  event of the transient `deleted` row version must not refuse that commit. This was found by the
  commit 4 PostgreSQL sync tests and fixed in this migration (the function now reads the series
  row at commit); `test_a_series_deleted_and_revived_in_one_transaction_commits_with_its_override_resent`
  covers it, and the existing test still proves that an active override under a series that ends the
  transaction deleted cannot commit.

## Failure and crash behavior

Both cascade writes and the forgetting scrub commit atomically. Tests: a connection killed by
`pg_terminate_backend` mid-cascade, a real subprocess that exits (`os._exit`) with the cascade
uncommitted, and a killed forgetting transaction. Each leaves every table fingerprint unchanged, and
the same operation succeeds when retried. A commit-time refusal (deferred triggers) rolls back the
whole transaction.

## What the database does not prove

* It cannot tell that a provider's sequence numbers are meaningful, or that a legal-looking cascade
  transition (series `deleted`, override `active` to `deleted` with the floor unchanged) is
  accompanied by a `calendar_changes` row with the matching `cascade_count`. That part is the page
  application algorithm (commit 4), checked there by row-level assertions on floor, flag, `deleted_at`
  and change rows. A buggy writer running as the runtime role can still skip the change row; it
  cannot produce a state in which floor and origin disagree.
* The cursor guard is a set of necessary conditions, not a proof (section 6.5). A statement that
  satisfies every condition with an arbitrary cursor is accepted, and one test asserts exactly that.
* `deleted_by_cascade` stays true after the series is revived (old overrides are not reactivated by
  design); it only affects how an item at that floor is classified.

## Clarifications and additions to revision 11 (all recorded for the PR description)

1. `calendar_overrides` carries `deleted_at` (revision 11 refers to preserving it but lists no
   column). Replacement start is `start_wall` (canonical wall identity, same pattern as
   `recurrence_id`) and `duration` is a single column whose unit follows the series kind.
2. Forgotten series and overrides keep their non-content `sequence` (the column is NOT NULL and is
   required unchanged by the guard); `recurrence_id` and `created_at` remain immutable.
3. Beyond the revision 11 list, the guards also require: `revision = OLD.revision + 1` and a
   non-decreasing `updated_at` on every update of series, overrides and sync state; a strictly
   increasing `sequence` on every non-forgetting series or override update; new sync-state rows start
   as `never` with empty counters; new series and override rows start at revision 1; `applied_seq`
   equals `max(seq)` on every sync-state update.
4. `recurrence_id` is the empty string for single events (decision recorded in commit 2); it does not
   appear in these tables.
5. A forgotten source's scrub requires every series and override to be `forgotten` (not merely
   not `active`), so tombstones lose their `uid` too.
6. Refusals use SQLSTATE 23514 with the rule name in `CONSTRAINT`, so tests assert the exact guard.
7. The deferred orphan trigger reads the series state at commit (defect found by the commit 4 sync
   tests: it refused a series deleted and revived within one page). Migration 0035 and this audit were
   corrected in place; nothing had been pushed or merged, so no released migration changed.
