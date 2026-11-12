# Batch 3 proposal: calendar recurrence and full briefing

Status: **proposal, not implemented.** Approved direction recorded 11 Nov 2026 (decisions D1 to D12 below carry the approved resolutions). Nothing in this document is authorization to push, open a PR or merge. Covers ORG-01, ORG-02, CORE-08, CORE-09, UI-01, MVP-02. **ORG-01 and MVP-02 stay partial** until a real-connector spike is completed.

Revision 2 (12 Nov 2026) resolves the review findings: DST semantics by instance origin (5.4), database-level ownership integrity (6.0 to 6.5), series and override lifecycle (6.7), cursor progress contract (7.1), tightened exclusivity trigger (6.6), and the clarifications in 5.7, 5.8, 6.8, 6.9, 7.3.1 and 9. Questions O1 to O5 are settled in section 14.

Revision 3 (12 Nov 2026) resolves the second review: overlap-aware expansion lookback derived from the duration contract (5.5, B1), instant-preserving handling of UTC `RDATE`/`EXDATE`/`RECURRENCE-ID` values in a DST fold (5.8, B2), an explicit provider dependency-order contract with a recovery path (7.1, 7.2, 7.3.2, B3), explicit blocked-source guarantees (7.3.2, 8.2, 8.3), O2 changed to dev/test only, and the test-list contradiction removed. O1 to O5 are now **settled** (section 14).

Revision 4 (12 Nov 2026) resolves the third review: a deterministic total order for independent items within a page, which also fixes `calendar_changes.seq` assignment (7.3.1, 6.8), and an honest statement of what the sync-state database guard does and does not guarantee, with a strengthened transition guard (6.5).

Revision 5 (12 Nov 2026) resolves the fourth review: one coherent page-application algorithm replacing the phase-only ordering (7.3.1: per-entity reduction, unknown-entity deletion semantics, override resolution against the series' final state, net change rows, deterministic write order), a narrowly defined forgetting transition in the sync-state guard (6.5), a canonical code list (7.3.3), proposal-only PR A (15), and consistency corrections.

Revision 6 (12 Nov 2026) applies seven specification corrections from the fifth review and changes no architecture, decision or limit (G2 and G3 add specified mechanisms to existing decisions): the exact sync-state columns of the forgetting transition (G1, 6.5), database-side strictly monotonic `last_success_at` and clock-skew behaviour (G2, 6.5), revalidation of untouched stored overrides (G3, 7.3.1 Step 3), the tombstone-total stall as a disclosed limitation (G4, 14), the higher-sequence revival exception in criterion 4 (G5, 16), the exact `content_hash` of delete rows (G6, 6.4), and why the forgetting exception is reachable only in the forgetting transaction (G7, 6.5 and 6.6), with matching tests.

Revision 7 (12 Nov 2026) resolves the review of revision 6 and changes no architecture, decision (D1 to D12, O1 to O5) or section 9 limit: (R1) an override **update** can never resolve a membership mismatch, only an explicit **deletion** of the stored override can (7.3.1 Step 3, 5.8, O3, tests); (R2) `blocked_detail` gains a `recurrence_digest` with an unambiguous length-prefixed encoding, exact NULL rules and a deterministic choice among several unmatched overrides (6.5, 7.3.2, tests); (R3) tombstone floor equality is a `sequence_conflict`, not stale (6.7, criterion 4, tests); and clarifications C1 to C10: the exact column set of the forgetting transition, the valid `UPDATE` expression and one monotonic `last_success_at` expression on every write, the freshness effect of forward clock drift, the accurate description of what the forgetting guard inspects, the literal `TOMBSTONE_HASH` vector, and the corresponding test wording.

Revision 8 (12 Nov 2026) resolves the review of revision 7 and changes no architecture, schema, decision (D1 to D12, O1 to O5) or section 9 limit, and keeps every fail-closed behaviour: (B1) the equal-floor rule is stated by floor origin, a delete-origin tombstone versus a cascade-tombstoned override whose floor is its own last upsert sequence, with any item at a cascade floor a `sequence_conflict`, disclosed as a limitation and a spike question (6.7, 7.3.1 Step 2, 13, 14, 17); (B2) unmatched overrides are selected by the total order `(series uid, recurrence_id)` in UTF-8 bytes over all candidates, stored or delivered (7.3.1 Step 3, 7.3.2, 13); and N1 to N9: only an applied delete with a strictly higher sequence resolves a mismatch, `blocked_detail` always carries six keys with JSON `null` for unavailable values and has NULL rules for malformed items, the key set is an application contract and not a database check, the `sync-status` response includes `blocked_detail`, the section 5.6 cross-reference and test wording, the forgetting-guard wording, and the resync protocol (fetch argument `since = None`, stored cursor untouched, T2 compare-and-swap against the stored cursor recorded in T1).

Revision 9 (12 Nov 2026) resolves the final review of revision 8 and changes no architecture, schema, decision (D1 to D12, O1 to O5) or section 9 limit: the multi-page pass is defined as one complete T1, fetch, T2 cycle per page with no claim held between pages and a pass that is not an exclusive reservation (F4, 7.1, 7.3, 7.4); the exact fields T2 resets on success are enumerated (F5, 7.3); a multi-page test is specified (F6, 13); the floor-origin tests now assert the full final row, the floor, the origin flag, `deleted_at` and the change row, including multi-version pages (F2, 13); the override-floor limitation is widened to every override item received while the series is deleted (F3, 7.3.1, 14); and the database backstop for the floor/flag coupling is **recorded as a mandatory audit item for the migration and trigger review, not as a new schema requirement of this proposal** (F1, 6.3, 15, 16).

Revision 10 (12 Nov 2026) resolves the final review of revision 9 and changes no architecture, schema, decision (D1 to D12, O1 to O5) or section 9 limit: (B-1) the owner-sync policy is decided and specified exactly: an explicit owner sync bypasses backoff and the failed/blocked skip but **never an unexpired lease**, T1 receives a non-persisted invocation-level `explicit` flag settable only by the owner `sync` route, an explicit sync of a `failed` source resets `attempts` to 0, of a `retry_wait` source preserves its attempts, a failed attempt counts and backs off normally, and the fifth failure sets `failed` with `next_attempt_at = NULL` (7.3 items 1 to 4 and the policy table, 6.5, 9, 10, 13, 16); N-1 an override delete under a deleted series creates no tombstone (7.3.1); N-2 `deleted_at` comparison semantics in the permutation tests (13); N-3 a floor-raising delete preserves the original `deleted_at` (6.7, 7.3.1, 13); and O-1 to O-4: the accepted application-level alternative is aligned across 6.3, 15 and 10j, `has_more = false` ends a pass, an owner sync requests one bounded pass and not repeated passes, and the provider fetch timeout must be shorter than the claim lease (7.3, 10, 13).

Revision 11 (12 Nov 2026) resolves the two blockers of the final review of revision 10 and changes no architecture, schema, decision, limit or policy: the unreachable 6 h backoff is removed, so the four delays are 30 s, 2 min, 10 min and 1 h after failures one to four and the fifth failure is terminal (7.3 item 4, 13), and the stale statement that an owner resync resets attempts is replaced by the decided policy that an explicit owner sync of a `failed` source resets them while `resync` only changes the fetch argument (13).

Baseline audited: `main` after PR #26 (merge `8824ae3`, migration head `0034_invoice_filing_execution`). All repository facts below were read from that tree; where a statement is a design choice or an unverified provider behaviour it is labelled as such.

Standing constraints: synthetic data only, no real account or credential, no external write, no model call, 068/069 workers not modified, routines' DST convention not modified.

---

## 1. Current implementation inventory (verified)

| Area | What exists today |
|---|---|
| Model | `calendar_sources` (one row per source, one JSONB `data` blob, `revision` 1..101, state active/forgotten) and `calendar_revisions` (a full snapshot per revision; history trigger requires `actor_id == owner` and `snapshot == parent.data`). Seal trigger `butler_seal_calendar` (migration 0026). Sources start `setup_required` at revision 1 with no window. At most 10 sources per owner. |
| Window contract (`calendar_contracts.py`) | Complete-only window, 1 to 31 local dates, at most 100 occurrences, at most 64 KiB, `fetched_at`, `cursor` (1 to 128 chars). Timed events carry aware instants whose offset must match the zone; all-day events carry `start_date` and exclusive `end_date`. Fields `uid`, `recurrence_id`, `sequence`, `status` (confirmed, tentative, cancelled). |
| Reconcile (`calendars.py`) | Expected revision, exact replay is a no-op, cursor-reuse conflict, monotonic `fetched_at` (60 s future tolerance), per-(uid, recurrence_id) sequence monotonic consulting history, equal sequence with changed content refused. `offline`/`failed` keep the last good window; stale after 24 h; unknown coverage reported. Deletion is inferred from absence in a complete window. |
| API (`calendar_routes.py`) | All `POST`: create, `/query`, `/briefing`, `/{id}/read`, `/import`, `/unavailable`, `/forget`, `/history`, `/export`. Owner and scope checked through `manual_tasks.authority`. |
| Briefing (`calendars.briefing`) | One day, one scope. Up to 25 sources, 100 events, 25 open tasks (overdue included), 10 confirmed memory refs. DST-aware day bounds. Overlap flag for timed events only. Occurrence id `uuid5(source.id, json.dumps([uid, recurrence_id]))`. |
| Frontend | `CalendarPanel.tsx`, `DailyOverviewPanel.tsx`, `daily-overview.ts` (client composes three separate reads), `calendars-api.ts`. |
| Workers | None for calendars. Existing workers: `reminder_worker`, `routine_worker` (compose services), `notification_worker` and `filing_worker` (dev/test, not started by default). |
| Tests | `tests/test_calendars.py` (11 test functions), `tests/integration/test_calendars_postgres.py` (6), `scripts/calendar-restore-fixtures.py`. Every briefing test uses Europe/Paris for both the event zone and the display zone. |
| Dependencies | `tzdata>=2026.6`; no `python-dateutil`, no `icalendar`, no CalDAV client. |

## 2. Gap analysis

| Id | Gap | Evidence | Closed by |
|---|---|---|---|
| G1 | **Defect.** An all-day event appears on two display days when the display zone differs from the event zone (section 3). | `contract.interval` / `calendars.briefing` | Commit 1 |
| G2 | No recurrence. | No RRULE, series or override concept | Commits 2 to 4 |
| G3 | Window capped at 100 occurrences and 64 KiB. | `Window.events max_length=100` | Relational provider mode |
| G4 | No poller or worker. | No calendar worker module | Commit 4 |
| G5 | Full-window replacement only; deletion inferred from omission. | `calendars.changes` | Explicit deletions in provider mode |
| G6 | 100-revision cap, full copy per revision. | `ck_calendar_revision` | Change rows in provider mode |
| G7 | No system actor in calendar history. | `actor_id` must equal owner | New `calendar_changes` (NULL system actor) |
| G8 | No provider interface. | none | Commit 2 |
| G9 | Briefing is exact-day only; duplicate sources appear only as an overlap flag. | `calendars.briefing` | Commit 5 |
| G10 | Recurrence wall-time DST semantics undefined; routines use a different convention. | `routine_contracts.py` | D4 |
| G11 | No real-process restart evidence for calendars (nor for the 068/069 workers). | tests | Commit 6 (calendars only) |
| G12 | Status documents behind #24 to #26. | ROADMAP, FEATURE_REGISTER, BACKLOG_STATUS, FEATURE_OVERVIEW, FEATURE_PROGRESS, FEATURE_DASHBOARD, FILING_EXECUTION title | Commit 7 of PR B (PR A contains only this proposal) |
| **G13** | **Silent truncation in the briefing.** `events[:100]`, `sources[:25]` and `tasks[:25]` slice with no truncation indicator, so with several sources more than 100 events are dropped without any signal. (Verified in `calendars.briefing`; found while writing this proposal.) | `calendars.py` | Commit 5 (explicit limit states, section 9) |

## 3. G1: verified all-day defect

**Root cause.** `contract.interval()` turns an all-day event into two UTC instants by taking midnight of its `start_date` and `end_date` in the **event's** zone (`midnight(date, event["timezone"])`). The briefing then tests overlap against the display day, which is an instant range `[start, end)` computed in the **display** zone. A calendar date is not an instant range. When the zones differ, midnight-to-midnight in the event zone spans parts of two display days, so the event overlaps both and is shown twice. Example: an all-day event on 5 March in Pacific/Auckland (UTC+13) overlaps 4 March and 5 March in Europe/Paris.

**Affected code paths.** `calendar_contracts.interval` (all-day branch), `calendars.briefing` (overlap test and the sort key), and the timed-only overlap sweep (all-day is already excluded from conflict flags). `contract.midnight` is also used for window coverage (`covers_day`), which is correct because coverage is about instants.

**Correction.** All-day events are matched by **calendar date**, never by instant: an all-day event belongs to display day `D` iff `start_date <= D < end_date` (exclusive end), regardless of either zone. Timed events keep the instant overlap rule. All-day events sort before timed events within a day. `interval()` keeps its current meaning for coverage and is no longer used to place all-day events.

**Regression tests (commit 1, written red first).** Event zone ahead of, behind and equal to the display zone; multi-day all-day event; event ending exactly at display-day boundary; asserts the event appears on exactly the expected dates and on no other. The existing Europe/Paris-only tests are unchanged and still pass.

## 4. Decisions D1 to D12: approved resolutions

| Id | Topic | Approved resolution |
|---|---|---|
| D1 | Rule representation | Structured recurrence rules internally; RFC 5545 RRULE semantics at provider boundaries. |
| D2 | Expansion engine | **`python-dateutil` behind our own interface.** No custom recurrence engine. Used only through `dateutil.rrule.rrule` constructed from validated structured fields (never `rrulestr`, never `dateutil.parser`, never `dateutil.tz`). |
| D3 | Rule subset | Explicit bounded subset of RFC 5545 (section 5). Anything else is rejected explicitly, never approximated. |
| D4 | `THISANDFUTURE` | Excluded; rejected explicitly. |
| D5 | DST and zone semantics | RFC 5545 calendar semantics **by instance origin** (section 5.4): §3.3.5 for explicit DATE-TIME values (`DTSTART`, `RDATE`, override replacement starts), §3.3.10 for RRULE-generated instances (nonexistent local times ignored and not counted toward `COUNT`). Routines unchanged. |
| D6 | G1 | Fixed first, in its own commit, with a regression test. |
| D7 | Storage | Five new relational tables (section 6); existing JSON blob not expanded. |
| D8 | Source modes | Provider mode and manual import are mutually exclusive, **enforced at database level** (section 6.6). |
| D9 | Bounds | The proposed numerical bounds, with **explicit limit and truncation states**. Never silently omit occurrences or changes; never advance a cursor past unapplied changes (sections 7.1 and 9). Limits are evaluated against the final state of a complete page (section 7.3.1). |
| D10 | Synthetic provider | File-backed, **SQLite-backed**, atomic, with genuine separate-process restart tests (section 7). |
| D11 | Briefing | Seven-day horizon, no inferred needs. |
| D12 | Delivery | Docs-first PR, then the seven-commit implementation PR with a **mandatory audit gate immediately after the migration commit**. |

Numbering note: these are the same twelve decisions as in the earlier Docs-page draft, re-ordered so the user's approval list maps one to one. The draft's older D2 (own expander) and D9 (config-gated file store, "preferably SQLite") are superseded here.

## 5. Supported RFC 5545 subset and rejection rules

### 5.1 Internal structured rule (stored in `calendar_series.rule`)

```
{"freq": "DAILY|WEEKLY|MONTHLY|YEARLY",
 "interval": 1..999,
 "by_day": ["MO".."SU", ...]        # WEEKLY only, no ordinal prefix
 "by_month_day": [1..31, ...]       # MONTHLY, YEARLY
 "by_month": [1..12, ...]           # YEARLY only
 "wkst": "MO".."SU"                 # default MO
 "count": 1..1000   XOR   "until": <date | UTC instant>}
```

Provider-boundary parsing converts an RRULE string to this form. Stored size at most 4 KiB; `exdates` and `rdates` are separate columns.

### 5.2 Accepted

DAILY, WEEKLY (with plain `BYDAY`), MONTHLY (with `BYMONTHDAY`, or implicit from DTSTART), YEARLY (implicit from DTSTART, or `BYMONTH`/`BYMONTHDAY`); `INTERVAL`; exactly one of `COUNT` or `UNTIL`, or neither (open-ended, only ever expanded inside a bounded query window); `WKST`; `EXDATE`; `RDATE` as DATE or DATE-TIME; `RECURRENCE-ID` overrides of a single instance; `STATUS` cancelled/tentative/confirmed.

### 5.3 Rejected explicitly (stable error code each, whole sync page refused)

| Construct | Code |
|---|---|
| `THISANDFUTURE` range | `range_thisandfuture` |
| `SECONDLY`, `MINUTELY`, `HOURLY` | `freq_unsupported` |
| `BYSETPOS`, `BYWEEKNO`, `BYYEARDAY`, `BYHOUR`, `BYMINUTE`, `BYSECOND` | `by_rule_unsupported` |
| Ordinal `BYDAY` (`1MO`, `-1FR`), negative `BYMONTHDAY` | `by_day_ordinal`, `by_month_day_negative` |
| `RSCALE`, `SKIP`, non-Gregorian scales | `rscale_unsupported` |
| `COUNT` together with `UNTIL`; `COUNT` over 1000; `INTERVAL` over 999 | `count_until_both`, `count_limit`, `interval_limit` |
| Unknown or duplicated rule part, `X-` rule parts | `rule_part_unknown`, `rule_part_duplicate` |
| `RDATE` as PERIOD | `rdate_period` |
| UTC-form `RDATE`/`EXDATE`/`RECURRENCE-ID` that is the **second** occurrence of an ambiguous wall time (fails the instant round-trip of 5.8) | `utc_value_ambiguous` |
| Any input that violates the strict boundary grammar (section 5.7): non-ASCII, whitespace, empty part or value, bad integer form, over 256 characters | `rrule_syntax` |
| Duplicate list item | `by_list_duplicate` |
| `BYDAY` with a frequency other than WEEKLY | `by_day_freq_unsupported` |
| `BYMONTHDAY` or `BYMONTH` with an incompatible frequency | `by_rule_freq_mismatch` |
| `UNTIL` earlier than `DTSTART`; `DTSTART` not generated by its own rule | `until_before_start`, `dtstart_not_synchronized` |
| `EXDATE`/`RDATE`/`RECURRENCE-ID` of the wrong value type or in another zone | `exdate_type_mismatch`, `rdate_type_mismatch`, `override_type_mismatch`, `zone_mismatch` |
| `UNTIL` whose value type differs from DTSTART | `until_type_mismatch` |
| Floating times, non-IANA or unknown `TZID` | `zone_floating`, `zone_unknown` |
| Override `RECURRENCE-ID` not a member of the final instance set (excluded, nonexistent generated time, outside the rule), evaluated on the final state of the page | `override_unmatched` |
| Override whose series is **unknown everywhere** (neither stored nor in the same page). An override of a series that is deleted, in the page or already stored, is **not** an error: it is superseded and counted (section 7.3.1) | `override_orphan` |

Rejection is atomic for the page: the page is not applied, the cursor does not move, the sync state becomes `blocked` with the code, and the source shows an explicit unavailable state (section 8.4). Recording per-item rejections and moving on is a possible later policy (settled against in O1, section 14).

### 5.4 Local-time semantics (D5), by instance origin

RFC 5545 has **two different rules** for local times that fall in a DST gap or fold, and which one applies depends on where the instance came from. They must not be mixed:

| Origin of the instance | Nonexistent local time (spring gap) | Ambiguous local time (autumn fold) | RFC |
|---|---|---|---|
| **Explicit DATE-TIME value**: `DTSTART`, an `RDATE` value, an override's own replacement start | Interpreted with the UTC offset in effect **before** the gap, so it lands later by the gap length | The **first** occurrence (earlier instant) | §3.3.5 |
| **Generated by the RRULE** (every instance after the first) | The instance is **ignored** and **does not count toward `COUNT`** | The **first** occurrence (§3.3.5 rule for ambiguous times) | §3.3.10 |
| **`DTSTART` as the first instance** | Always the first instance and always counts as 1 (`COUNT` text of §3.3.10), even if its wall time does not exist; then the §3.3.5 interpretation applies to it | Same as above | §3.3.10, §3.3.5 |
| **`EXDATE` / `RECURRENCE-ID`** | Not interpreted as instants at all: they **identify** an instance by wall-clock value (section 5.8) | same | §3.8.5.1, §3.8.4.4 |

Further rules:

* Recurrence is computed on **wall-clock time in the event's IANA zone**, then localized per instance.
* Invalid generated dates (31 February, 29 February in a non-leap year) are ignored and not counted, exactly like nonexistent generated times (§3.3.10). They are never clamped.
* `COUNT` counts instances produced by the rule **before** `EXDATE` removal; `RDATE` values are **not** counted; skipped (ignored) generated instances are **not** counted; `DTSTART` is counted.
* Duration of a timed instance equals the master's exact duration in seconds.
* All-day events are dates; no zone arithmetic. `end_date` is exclusive.
* `UNTIL` given as a UTC instant is compared with each localized instance's instant; given as a date it is compared with the date.
* Routines keep their own convention (a gap has no instant, a fold takes the earlier instant). That convention is unchanged; the difference is documented in spec 070 and tested in both directions.

**Worked example 1: generated instance in the gap is skipped and does not consume `COUNT`.**
`Europe/Paris`, `DTSTART;TZID=Europe/Paris:20260315T023000`, `RRULE:FREQ=WEEKLY;COUNT=4`. Clocks move from 02:00 to 03:00 on Sunday 2026-03-29.

| Generated wall time | Exists? | Counted | Instant (UTC) |
|---|---|---|---|
| 2026-03-15 02:30 (DTSTART) | yes (+01:00) | 1 | 01:30Z |
| 2026-03-22 02:30 | yes (+01:00) | 2 | 01:30Z |
| 2026-03-29 02:30 | **no, in the gap** | **skipped, not counted** | none |
| 2026-04-05 02:30 | yes (+02:00) | 3 | 00:30Z |
| 2026-04-12 02:30 | yes (+02:00) | 4 | 00:30Z |

Result: exactly four instances (15 Mar, 22 Mar, 5 Apr, 12 Apr). Their `recurrence_id` values are the generated wall times (`2026-03-15T02:30:00`, ...). **Wrong behaviour that tests must reject:** shifting 29 Mar to 03:30 and counting it, which would end the series on 5 Apr with an instance at 2026-03-29 03:30 that RFC 5545 §3.3.10 says must not exist.

**Worked example 2: explicit `DTSTART` in the gap.**
`DTSTART;TZID=Europe/Paris:20260329T023000`, `RRULE:FREQ=WEEKLY;COUNT=3`. `DTSTART` is the first instance and counts; its explicit time is interpreted with the pre-gap offset (+01:00), i.e. 01:30Z (displays as 03:30 CEST). Then 2026-04-05 02:30 (+02:00, 00:30Z) and 2026-04-12 02:30. Three instances. The first instance's `recurrence_id` is the original `2026-03-29T02:30:00`, so it stays stable.

**Worked example 3: ambiguous generated time takes the first occurrence.**
`DTSTART;TZID=Europe/Paris:20261018T023000`, `RRULE:FREQ=WEEKLY;COUNT=3`. Clocks move from 03:00 back to 02:00 on 2026-10-25. Instances: 2026-10-18 02:30 (+02:00, 00:30Z); 2026-10-25 02:30 occurs twice and the **first** (CEST, +02:00, 00:30Z) is used; 2026-11-01 02:30 (+01:00, 01:30Z).

**Worked example 4: `RDATE` in the gap.** An `RDATE;TZID=Europe/Paris:20260329T023000` is an explicit DATE-TIME: it is interpreted with the pre-gap offset (01:30Z). It is added to the set, is not counted toward `COUNT`, and is deduplicated against any generated instance with the same wall time (impossible here, since the generated one was skipped).

**Worked example 5: modified override.** An override of the 2026-04-05 instance (`RECURRENCE-ID` 2026-04-05T02:30) that moves it to `20260329T023000` Europe/Paris: the replacement start is an explicit DATE-TIME, interpreted per §3.3.5 (01:30Z). The override's identity (`recurrence_id`) is still `2026-04-05T02:30:00`. An override naming `RECURRENCE-ID` 2026-03-29T02:30 (the skipped generated instance) is refused `override_unmatched`.

### 5.5 How `python-dateutil` is used (D2)

* Our module `calendar_recurrence.py` is the only importer of `dateutil`; a static test asserts that no other module imports it and that `rrulestr`, `dateutil.parser` and `dateutil.tz` are never imported anywhere.
* The rule is validated (sections 5.3, 5.7) **before** a `dateutil.rrule.rrule` object is built from structured fields. `dateutil` never sees an untrusted string.
* `rrule` runs on **naive wall times** (`dtstart` naive). `dateutil` does calendar arithmetic only; gap, fold and ambiguity handling is ours, applied after generation, so dateutil's own timezone-aware behaviour is never relied on.
* **`COUNT` and `UNTIL` are never passed to dateutil.** dateutil counts naive wall times, which would count nonexistent generated times and contradict section 5.4. Our driver pulls naive walls from an unbounded `rrule`, localizes each, drops the nonexistent ones (except `DTSTART`), counts the rest up to `COUNT`, and applies `UNTIL` to instants. dateutil's own skipping of invalid dates (31 February) agrees with RFC 5545 and is asserted by golden tests, not assumed.
* Scan is bounded: with `COUNT` the driver scans from the start (at most 1,000 counted plus skipped candidates); without `COUNT` it uses `rrule.between()` on a naive **overlap-aware** window (position independent, so a series started years ago is not rescanned). The window is derived from the duration contract, not from an arbitrary margin: a timed series may last up to `MAX_TIMED_DURATION = 2,678,400 s` (31 days, the `duration_seconds` check of 6.2), so an instance can start up to 31 days before the query start and still overlap it. The candidate wall window is therefore `[query_start_wall - LOOKBACK, query_end_wall + LOOKAHEAD]` in the series zone, where `LOOKBACK = MAX_TIMED_DURATION + GAP_ALLOWANCE` and `LOOKAHEAD = GAP_ALLOWANCE`, and `GAP_ALLOWANCE = 2 days` covers the largest offset change between a wall time and its instant. Each candidate is then localized (5.4) and kept only if its exact instant interval overlaps the query (`start < query_end` and `end > query_start`, end exclusive). All-day series use `LOOKBACK = 31 days` (`duration_days` maximum) with no allowance, because they are date-based. `MAX_TIMED_DURATION` and `MAX_ALLDAY_DAYS` are **single constants shared with the contract check and the database check**, and a test asserts the expander imports them rather than redefining them. A test over every IANA zone in the pinned `tzdata` (bounded sweep of 1970 to 2100) asserts that no offset change within a 33-day span exceeds `GAP_ALLOWANCE`, so a future tzdata change cannot silently invalidate the bound. Overrides are not found through the window: all (at most 100) active overrides of the series are considered separately, so an instance moved into the window from outside it appears and one moved out disappears. In both cases at most **5,000 candidate wall times per series per call** are examined; exceeding that returns `truncated` with reason `scan_limit`, never a silent short result.
* Pin: `python-dateutil>=2.9.0.post0,<3` in `backend/pyproject.toml` and `backend/uv.lock`, added in commit 2 (sole transitive dependency `six`, to be verified in the lock then). Supply-chain review is part of the audit gate.
* The expander is tested against golden cases derived from RFC 5545 text, not from dateutil output, so a dateutil quirk cannot hide in the oracle.

### 5.6 Stable occurrence identity

* `occurrence_id = uuid5(source.id, json.dumps([uid, recurrence_id], ensure_ascii=False))`: the existing scheme, unchanged.
* For a recurring instance `recurrence_id` is the canonical **original generated wall time in the series zone** (`YYYY-MM-DDTHH:MM:SS`) for timed events, or `YYYY-MM-DD` for all-day. It is the wall time **before** any gap or fold interpretation and **before** any override move, so it is stable across tzdata updates, across moving an instance, and across resynchronization.
* A non-recurring event uses `recurrence_id = null`, matching the legacy form `[uid, null]`.
* The id depends only on `(source.id, uid, recurrence_id)`. It is therefore **identical across deletion and revival** of the series or of an override: a tombstoned series keeps its `uid` and row `id`, a revival reactivates the same row, and no id is minted from row ids, timestamps or sequence numbers.
* Provider and manual sources never share a source id, so ids cannot collide across modes.

### 5.7 Strict grammar of the RRULE boundary parser

The parser takes the **value of one `RRULE` property** (no `RRULE:` prefix, no line folding). Parsing ICS or CalDAV text is out of scope; the synthetic provider supplies the RRULE, `EXDATE` and `RDATE` value strings so that this boundary is genuinely exercised.

```
rrule  = part *(";" part)
part   = name "=" value
name   = "FREQ" / "INTERVAL" / "COUNT" / "UNTIL" / "BYDAY" / "BYMONTHDAY" / "BYMONTH" / "WKST"
```

* ASCII only; any other character is `rrule_syntax`. No whitespace anywhere. At most 256 characters.
* Names are matched case-insensitively and normalized to upper case. Each name at most once (`rule_part_duplicate`); `FREQ` required. Any other name is `rule_part_unknown` (or the specific code in section 5.3).
* No empty part (leading, trailing or doubled `;`), no empty value, no empty list item (`rrule_syntax`).
* Integers match `[1-9][0-9]*`: no sign, no leading zero, no whitespace, at most 4 digits, then range-checked (`INTERVAL` 1 to 999, `COUNT` 1 to 1000).
* Lists are comma separated, at most 31 items, no duplicate item (`by_list_duplicate`); stored sorted.
* `BYDAY` items are exactly `MO TU WE TH FR SA SU` (ordinal prefixes rejected); `BYMONTHDAY` 1 to 31; `BYMONTH` 1 to 12; `WKST` one weekday.
* `UNTIL` is `YYYYMMDD` (a real Gregorian date) or `YYYYMMDDTHHMMSSZ` (real date, seconds 0 to 59, UTC). Floating `UNTIL` is rejected. Its type must match `DTSTART` (`until_type_mismatch`) and it must not precede `DTSTART` (`until_before_start`).
* Combinations: `BYDAY` only with `WEEKLY` (`by_day_freq_unsupported`); `BYMONTHDAY` only with `MONTHLY` or `YEARLY`; `BYMONTH` only with `YEARLY` (`by_rule_freq_mismatch`). Defaults: weekly without `BYDAY` uses the `DTSTART` weekday; monthly without `BYMONTHDAY` uses the `DTSTART` day; yearly uses the `DTSTART` month and day.
* **Synchronization of `DTSTART` with the rule:** the `DTSTART` wall time must itself be generated by the rule (for example a weekly `BYDAY=MO` series cannot start on a Tuesday), otherwise `dtstart_not_synchronized`. RFC 5545 leaves this undefined, so it is rejected, not guessed.
* The parser is pure and total: any input yields a structured rule or a typed error, never another exception and never unbounded work. `parse(serialize(rule)) == rule` for every valid rule. Tests include a bounded fuzz over random ASCII and non-ASCII strings.

### 5.8 `EXDATE`, `RDATE`, overrides: type matching and precedence

* **Type matching.** The `DTSTART` value type fixes the series kind. All-day series: `EXDATE`, `RDATE` and `RECURRENCE-ID` must be DATE (`YYYYMMDD`). Timed series: DATE-TIME, either local in the series zone (a `TZID` naming a different zone is `zone_mismatch`) or UTC with `Z`. **UTC-form values are accepted only if they survive an instant round-trip**: convert the instant to a wall time in the series zone, convert that wall time back with the §3.3.5 interpretation (first occurrence for an ambiguous time), and require the original instant. This is lossless because identity is the wall time and the accepted instant is exactly the one that wall time denotes. Consequently, in the Europe/Paris autumn fold of 2026-10-25, `2026-10-25T00:30:00Z` (the first 02:30, CEST) is accepted and identified as wall `2026-10-25T02:30:00`, while `2026-10-25T01:30:00Z` (the second 02:30, CET) is **rejected** as `utc_value_ambiguous`; two distinct instants are never silently collapsed into one occurrence, and a value that cannot be represented is never approximated. An unambiguous UTC value (for example `2026-10-25T10:00:00Z`, wall 11:00) is accepted and identified by its wall time. The same rule applies to `EXDATE`, `RDATE` and `RECURRENCE-ID`, so identity and override matching use one representation. Floating values and DATE-versus-DATE-TIME mixes are rejected (`exdate_type_mismatch`, `rdate_type_mismatch`, `override_type_mismatch`). `RDATE` as PERIOD is rejected.
* **Identity.** `EXDATE` and `RECURRENCE-ID` match an instance by its **wall-clock identity**, never by instant.
* **Precedence (set algebra).** `instances = (DTSTART ∪ rule-generated ∪ RDATE) − EXDATE`, deduplicated by wall identity. `EXDATE` wins over both the rule and `RDATE`. Identity is the wall time, so two members of the set can denote the **same instant** with different identities (for example an explicit local `RDATE` of a nonexistent 02:30 that resolves to 01:30Z, and a member whose wall time is 03:30 CEST, also 01:30Z); they remain two occurrences with distinct stable ids and are not merged (the briefing may flag them as possible duplicates). An `EXDATE` that matches nothing is stored and harmless (RFC 5545 permits it); it is counted in diagnostics, not an error. `EXDATE` never changes `COUNT`; an excluded `DTSTART` still counted as instance 1.
* **Overrides apply last**, to members of the final set only. An override whose `RECURRENCE-ID` is not a member (excluded, skipped because nonexistent, outside the rule, or absent) is `override_unmatched`. Overrides are validated against the **final state of the page** (series and overrides delivered together are evaluated together). A series change that would orphan an existing override is refused as a whole page (`override_unmatched`) unless the same page explicitly **deletes** that override with a strictly higher sequence than the stored one (a stale or equal-sequence delete does not remove it); updating it, including cancelling it, does not help because its `recurrence_id` is its identity (settled as O3, section 14).
* **Override effects.** `status: cancelled` hides the instance (counted in `cancelled_count`); otherwise the override replaces start (explicit DATE-TIME, §3.3.5), duration and title. A moved instance is emitted at its new time, so expansion must consider overrides separately from the rule (an instance moved into a query window from outside it must appear, and one moved out must not).
* Limits: 100 `EXDATE` and 100 `RDATE` per series.

## 6. Data model: migration 0035 (five new tables)

### 6.0 Integrity principles

* **Ownership and scope are enforced by the database through a chain of composite foreign keys**, not by application checks alone. The chain is: `calendar_sources(id, owner_id, scope_key)` ← `calendar_provider_links` ← `calendar_series` / `calendar_sync_state` / `calendar_changes` ← `calendar_overrides`. Every child row therefore carries `source_id`, `owner_id` and `scope_key` that must equal its parent's; a mismatch cannot be inserted by any role.
* **Additive DDL on the sealed `calendar_sources`** (reviewed at the audit gate): one new unique index `uq_calendar_source_identity (id, owner_id, scope_key)` (the target of the composite foreign key; always satisfied because `id` is already unique) and the triggers of section 6.6. No existing column, function or trigger of `calendar_sources` or `calendar_revisions` is changed.
* **Immutable identity.** A trigger on each new table refuses updates to `id`, `source_id`, `owner_id`, `scope_key`, `series_id`, `recurrence_id` and `created_at`, and to `uid` except the forgetting transition to NULL.
* Rows are never physically deleted (no DELETE, no TRUNCATE for any role, enforced by trigger); deletion is a tombstone state. The runtime role gets only the grants listed per table.
* Every new table carries `owner_id` (FK `users`) and `scope_key` (check against the three scopes).

### 6.1 `calendar_provider_links`

| Column | Type | Notes |
|---|---|---|
| `source_id` | uuid PK | one link per source |
| `owner_id`, `scope_key` | as above | **composite FK `(source_id, owner_id, scope_key)` → `calendar_sources(id, owner_id, scope_key)`**; `UNIQUE (source_id, owner_id, scope_key)` is the parent key for all children |
| `provider_kind` | varchar(16), check `IN ('synthetic')` | only the synthetic kind in this batch |
| `provider_ref` | varchar(64) NULL, check `provider_ref ~ '^[a-z0-9_-]{1,64}$'` | opaque handle, never a path or URL; NULL only after the source is forgotten (section 6.9) |
| `created_at` | timestamptz | |

Insert is allowed only while the source is `active`, `revision = 1` and `data->>'status' = 'setup_required'` (never imported). The row is otherwise immutable; the single allowed update is `provider_ref` to NULL while the source is `forgotten`. Grants: SELECT, INSERT, `UPDATE (provider_ref)`.

### 6.2 `calendar_series`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `source_id`, `owner_id`, `scope_key` | | **composite FK → `calendar_provider_links(source_id, owner_id, scope_key)`**, so a series can exist only for a provider-mode source and always matches its owner and scope; `UNIQUE (id, source_id, owner_id, scope_key)` is the parent key for overrides and changes |
| `uid` | varchar(255) NULL | non-NULL unless `state = 'forgotten'` (check); `UNIQUE (source_id, uid)` |
| `state` | check `IN ('active','deleted','forgotten')` | `deleted` is a tombstone that refuses stale redelivery |
| `kind` | check `IN ('timed','all_day')` | content column |
| `status` | check confirmed/tentative/cancelled | content column |
| `sequence` | integer, check `>= 0` | monotonic; kept on tombstones as the floor |
| `title` | varchar(160) | the only display field of the existing `Event` contract (`title`, 1 to 160 characters); content column |
| `start_local` | timestamp (naive) | timed; wall time in `zone` |
| `start_date` | date | all-day |
| `zone` | varchar(64) | IANA name or `UTC`; NULL for all-day |
| `duration_seconds` | integer, check `1..2678400` | timed |
| `duration_days` | integer, check `1..31` | all-day |
| `rule` | jsonb NULL, check `octet_length(rule::text) <= 4096` | NULL means a single event |
| `exdates`, `rdates` | jsonb arrays, each at most 100 entries | canonical wall strings or dates |
| `provider_version` | varchar(128) NULL | opaque |
| `revision` | integer | monotonic +1 per change |
| `created_at`, `updated_at`, `deleted_at` | timestamptz | `deleted_at` set exactly when `state = 'deleted'` |

Check: all content columns are non-NULL exactly when `state = 'active'`; a tombstone keeps `uid`, `sequence`, `deleted_at` only; a forgotten row keeps nothing. Index `(source_id, state)`. Limits (section 9): at most 200 **active** and 400 **total** series rows per source, enforced by a trigger that first takes `FOR UPDATE` on the source row and then counts. Grants: SELECT, INSERT, UPDATE.

### 6.3 `calendar_overrides`

Per-instance exception, move or cancellation.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | `UNIQUE (id, source_id, owner_id, scope_key)` for change references |
| `series_id`, `source_id`, `owner_id`, `scope_key` | | **composite FK → `calendar_series(id, source_id, owner_id, scope_key)`**: the override's series, source, owner and scope always belong together |
| `recurrence_id` | varchar(32) | canonical original wall time or date (section 5.6); `UNIQUE (series_id, recurrence_id)` |
| `state` | check `IN ('active','deleted','forgotten')` | |
| `deleted_by_cascade` | boolean | true when tombstoned because its series was deleted (section 6.7) |
| `status` | check confirmed/tentative/cancelled | content column; `cancelled` hides the instance |
| `sequence` | integer | monotonic; kept on tombstones as the floor |
| moved / changed fields | nullable | replacement start, duration, title; NULL inherits from the series; content columns, NULL unless `active` |
| `revision`, timestamps | | |

Trigger: an override may be `active` only while its series is `active`. **Audit item (F1), recorded and not a new schema requirement of this proposal:** `deleted_by_cascade` decides whether an item at a tombstone's floor is a counted replay or a `sequence_conflict` (sections 6.7 and 7.3.1 Step 2), so the coupling between the floor and its origin flag is behaviour-bearing. In this batch it is enforced by the page-application algorithm only. The migration and trigger audit after commit 3 (section 15) must decide whether the database also enforces it, for example that the flag is true only while `state = 'deleted'`, that a tombstone's `sequence` changes only together with the flag becoming false, and that the flag becomes true only in the active-to-deleted cascade transition with `sequence` unchanged, and must add the matching direct-SQL negative tests if it does. **Accepted application-level alternative (O-1):** the audit may instead accept enforcement by the page-application algorithm alone, but only by recording that decision together with its evidence (the row-level floor, flag, `deleted_at` and change-row assertions of section 13 that pass, and an explicit statement that direct SQL by the restricted runtime role is not prevented from breaking the coupling) and the tests that carry it; a decision without recorded evidence and tests is not an accepted alternative, and an invariant enforced by neither the database nor such an accepted alternative is a completion blocker (section 15, criterion 10j). Limits: at most 100 **active** and 200 **total** override rows per series (same locking pattern). Grants: SELECT, INSERT, UPDATE.

### 6.4 `calendar_changes` (append-only history)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `source_id`, `owner_id`, `scope_key` | | **composite FK → `calendar_provider_links`** |
| `seq` | integer, `UNIQUE (source_id, seq)`, check `1..5000` | **gapless per source**, allocation in section 6.8 |
| `entity` | check `IN ('series','override')` | |
| `series_id` / `override_id` | uuid NULL | **exactly one non-NULL, matching `entity`** (check); composite FKs `(series_id, source_id, owner_id, scope_key)` → `calendar_series` and `(override_id, source_id, owner_id, scope_key)` → `calendar_overrides`, so the referenced entity must belong to the same source, owner and scope. No `uid` or `recurrence_id` copy is stored: they are read from the referenced row, so they cannot disagree with it |
| `operation` | check `IN ('upsert','delete','revive')` | `revive` reactivates a tombstone with a higher sequence |
| `sequence` | integer | the **highest applied sequence** of the entity in that page |
| `cascade_count` | integer, default 0 | number of overrides tombstoned by a series `delete` (section 6.7) |
| `content_hash` | char(64) NOT NULL | SHA-256 of canonical content for `upsert` and `revive`. For **every `delete` row** (explicit delete, cascade-owning series delete, tombstone creation and floor raise) it is the fixed constant `TOMBSTONE_HASH`: the SHA-256 of the exact UTF-8 byte string `butler.calendar.tombstone.v1` (no trailing newline), written as 64 lowercase hexadecimal characters, `136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01`. It is defined once in the shared module and is independent of any content, so delete rows are deterministic and comparable across permutations. A test asserts the **literal** vector above (not a recomputation) and that no `delete` row carries another value |
| `snapshot` | jsonb NULL | NULL after forgetting |
| `actor_id` | uuid NULL, **check `actor_id IS NULL`** | every change in this batch is made by the system worker; no owner-initiated change rows exist yet, so the column is reserved and always NULL |
| `sync_run_id` | uuid | groups one applied page |
| `cursor_after` | varchar(512) | cursor value after this page |
| `applied_at` | timestamptz | |

**One row per entity per page** (the net transition of stored state, section 7.3.1; intermediate versions inside one page are not stored separately). Unique index `(source_id, entity, COALESCE(series_id, override_id), sequence, content_hash)` refuses duplicate application even in a race. Append-only: update refused except `snapshot` to NULL while the source is `forgotten` (the same privacy-preserving redaction as filing history in 0034); delete and truncate always refused. At most 5,000 rows per source. Grants: SELECT, INSERT, `UPDATE (snapshot)`.

### 6.5 `calendar_sync_state`

| Column | Type | Notes |
|---|---|---|
| `source_id`, `owner_id`, `scope_key` | | `source_id` PK; **composite FK → `calendar_provider_links`**, so sync state always matches its source's owner and scope |
| `status` | check `IN ('never','ok','retry_wait','failed','blocked')` | `claimed` is a lease on top of status, not a status |
| `cursor` | varchar(512) NULL | NULL = initial; the provider's opaque cursor |
| `applied_seq` | integer | **the sequence counter**: highest `calendar_changes.seq` for the source (section 6.8) |
| `claim_token` | uuid NULL, `claim_expires_at` timestamptz NULL | lease, default 120 s (configurable down to 1 s in tests) |
| `attempts` | integer, check `0..5` | |
| `next_attempt_at` | timestamptz NULL | |
| `last_attempt_at`, `last_success_at` | timestamptz NULL | |
| `blocked_reason` | varchar(32) NULL, check against the canonical list of section 7.3.3 | exactly the codes listed there (shared module; a test asserts the database check and the module agree) |
| `blocked_detail` | jsonb NULL, check `octet_length(blocked_detail::text) <= 1024` | sanitized diagnostic for a blocked page (section 7.3.2): `code`, `entity` (`page`, `series` or `override`), `item_index`, `sequence`, `uid_digest`, `recurrence_digest`, defined exactly in section 7.3.2 (digest encoding and the NULL rules for each field); **never event content, never a raw `uid` or `recurrence_id`**; NULL unless `status = 'blocked'`; cleared on success and on forgetting. The database check is **only a size bound**: the key set and the `null` semantics are an application contract (one shared builder, section 7.3.2) verified by tests, not validated by the database |
| `last_error_code` | varchar(32) NULL, check against section 7.3.3 | `provider_unavailable`, `provider_timeout` |
| `revision`, `updated_at` | | |

**What the database guard does and does not guarantee.** Cursor correctness (that a stored cursor corresponds to exactly the changes committed with it) is guaranteed by the **worker's claim, fetch and apply protocol** in a single transaction (section 7.3) and demonstrated by the crash tests; **the database cannot prove it**, because an opaque provider cursor carries no verifiable relation to the change log. The runtime role is the application's own identity, so the database also cannot distinguish a worker from other code running as that role. The trigger is therefore a set of **necessary-condition checks that make accidental or out-of-protocol cursor changes fail**, not a proof:

* `cursor` may change **in the worker transition** only in a statement that **also** (a) releases a claim that the row held (`OLD.claim_token IS NOT NULL` and `NEW.claim_token IS NULL`), (b) **strictly advances** `last_success_at` (`NEW.last_success_at > OLD.last_success_at`, or `OLD.last_success_at IS NULL`; the value is produced by the single expression of the next bullet), and (c) leaves `applied_seq` equal to `COALESCE(max(seq),0)` of `calendar_changes` for the source, with `applied_seq` **never decreasing, never exceeding `max(seq)`** and increasing only together with the matching change rows. A bare `UPDATE ... SET cursor = ...` by the runtime role is refused, **including when `applied_seq` already equals the maximum sequence**. An owner resync never writes the cursor itself (it only changes the fetch argument, section 7.1), so it needs no exception to this guard;
* **`last_success_at` is written by exactly one expression, on every write** (a cursor-advancing apply, an empty page with an advanced cursor, and the caught-up path alike). In the `UPDATE` statement it is `last_success_at = GREATEST(clock_timestamp(), COALESCE(last_success_at, '-infinity'::timestamptz) + interval '1 microsecond')`: in an `UPDATE ... SET` expression the bare column name denotes the **pre-update** value (`OLD.` exists only inside trigger bodies, where the guard compares `NEW.last_success_at > OLD.last_success_at`). `timestamptz` has microsecond resolution, so the one-microsecond step is exact, `'-infinity' + interval` stays `-infinity`, and a NULL old value yields `clock_timestamp()`. Strict advance therefore holds by construction even if the database clock stalls, repeats a value or is stepped backwards; concurrent writers are serialized by the locked sync-state row, so the old value read is the committed one; a retry recomputes it. No application clock is involved, so a frozen application clock cannot break this path. **Clock skew:** after a backwards step `last_success_at` can sit ahead of real time. The application computes ages from `last_success_at` with an injectable clock and **clamps a negative age to 0**, so a skewed value never produces a negative age. The effect is on freshness labels: a forward-drifted `last_success_at` can make data look **fresher** than it is, by up to the size of the drift, and delays the 24-hour stale label by the same amount (never earlier). It never makes the statement fail, because a failing guard would stall a healthy source. The 24-hour stale test sets the injected application clock, not the database clock;
* **The one other permitted cursor change is the forgetting transition**, defined exactly: `cursor` becomes NULL only in a statement that sets the **terminal state** and only while the parent `calendar_sources` row **reads as `forgotten`** (the guard reads the row's state; it does **not** and cannot inspect transaction identity; the forget statement updates the source first). The terminal state is the conjunction `status = 'blocked'`, `blocked_reason = 'source_forgotten'`, `cursor IS NULL`, `claim_token IS NULL`, `claim_expires_at IS NULL`, `blocked_detail IS NULL`, `next_attempt_at IS NULL`, and `applied_seq` **unchanged**. **The statement changes exactly these columns and no others:** the terminal-state columns above plus `revision` (`NEW.revision = OLD.revision + 1`) and `updated_at` (`NEW.updated_at >= OLD.updated_at`). `source_id`, `owner_id`, `scope_key`, `applied_seq`, `attempts`, `last_attempt_at`, `last_success_at` and `last_error_code` are **unchanged** (`last_error_code` holds only a code, never content). In particular the statement cannot keep a non-NULL cursor, change `applied_seq` or `last_success_at`, or move to a non-terminal status. Once the row is terminal, **every further update is refused**. Setting the terminal state while the source does not read as `forgotten`, or setting `cursor` to NULL outside this transition, is refused. **Reachability (G7, C10):** the guard accepts the transition when the source row reads as `forgotten`, as it does inside the forgetting transaction; it does not know which transaction made it so. The protection is the combination of three database rules: the exclusivity trigger of 6.6 lets a source become `forgotten` only through the exact forgetting transition; the deferred scrub-completeness trigger of 6.6 refuses that transaction's commit unless this terminal sync state, the scrubbed series and overrides and the NULL `snapshot`, `uid` and `provider_ref` are all present; and a terminal row is immutable. So the exception is unreachable outside the forgetting transaction: before it the source does not read as `forgotten` (the check fails), and after it commits the row is already terminal (every further update is refused, which is also what stops a later transaction from re-using the exception). A forget without a scrub fails at commit. This exception is narrow by construction and does not weaken the general guard;
* `status`, `blocked_reason` and `blocked_detail` are consistent (`blocked_reason` required exactly when `status = 'blocked'`); `attempts` resets only on success, or to 0 when an explicit owner sync claims a `failed` source (section 7.3 item 1);
* the guard does **not** claim that a statement satisfying the worker-transition conditions carries the right cursor value; a compromised or buggy component acting as the runtime role could still forge a consistent update. That residual risk is accepted for the synthetic MVP, is stated in the limitations, and is mitigated by the tests and the audit gate, not by the trigger.

Grants: SELECT, INSERT, UPDATE.

### 6.6 Mutual exclusivity at the database level (D8), tightened

The additive trigger `butler_calendar_provider_exclusive` (`BEFORE UPDATE` on `calendar_sources`) applies to a row **only if a provider link exists for it**. For such a row it **refuses every update except the one legitimate forgetting transition**, defined exactly as the conjunction of:

* `OLD.state = 'active'` and `NEW.state = 'forgotten'`;
* `NEW.data IS NULL`;
* `NEW.revision = OLD.revision + 1`;
* `NEW.updated_at >= OLD.updated_at`;
* `ROW(NEW.id, NEW.owner_id, NEW.scope_key, NEW.created_at) IS NOT DISTINCT FROM ROW(OLD.id, OLD.owner_id, OLD.scope_key, OLD.created_at)`.

Those are all eight columns of the table (`id`, `owner_id`, `scope_key`, `state`, `revision`, `data`, `created_at`, `updated_at`); no other change is possible, so an `UPDATE` that sets `state = 'forgotten'` cannot carry any unrelated modification: `data` must be NULL, identity columns must be unchanged, and the revision must advance by exactly one. Any other update of a linked row (manual import, `unavailable`, any change to `data`, `label`, `revision`) and any update of an already `forgotten` row is refused.

A second, **deferred** constraint trigger (`AFTER UPDATE`, `DEFERRABLE INITIALLY DEFERRED`) on the same table checks, at commit, that a linked source that became `forgotten` has been completely scrubbed in the same transaction (section 6.9): no `active` series or override, no non-NULL `snapshot`, `uid`, `provider_ref` or `blocked_detail`, and a terminal sync state. A forget that does not scrub cannot commit. Together with the forgetting-only update rule above and the immutability of a terminal sync-state row, this is why the forgetting exception of 6.5 cannot be used outside the forgetting transaction: the source can become `forgotten` only through the exact transition, that transition cannot commit without the terminal sync state, and afterwards the row cannot be updated.

`calendar_provider_links` insert is refused unless the source is `active`, `revision = 1`, `setup_required` and unforgotten. The manual API additionally returns a stable 409 (`calendar.provider_mode`) before reaching the trigger. The existing functions and triggers (`butler_seal_calendar`, `butler_calendar_history_guard`) remain unchanged and keep applying to every row.

### 6.7 Series deletion, revival and override lifecycle

**Delete (explicit provider delete with a sequence higher than the stored one):**

* The series becomes `deleted`: content NULL, `deleted_at` set, `sequence` updated to the delete's sequence (the floor).
* In the **same transaction every `active` override of that series is tombstoned** (`state = 'deleted'`, `deleted_by_cascade = true`, content NULL). Each keeps its `recurrence_id` and its own `sequence` as a floor. For a cascade tombstone that floor is the sequence of the override's **last upsert**, not of a delete (`deleted_by_cascade = true` records this origin).
* **One** change row is written (`operation = 'delete'`, entity `series`) with `cascade_count = n` (or `revive` with `cascade_count = n` when a higher upsert in the same page reactivates the series; section 7.3.1); the cascade does not append `n` rows, which keeps the change-log budget bounded and predictable. The tombstoned override rows carry the evidence.
* An `active` override under a non-`active` series is impossible (trigger of 6.3).
* Cascade-tombstoned and explicitly deleted overrides **do not count toward the 100-active limit**. They count only toward the 200-total limit per series (and tombstoned series toward the 400-total limit per source), so tombstones cannot grow without bound; exceeding a total limit is `tombstone_limit`, a blocked page.

**Revive (an upsert for a `deleted` series with a sequence strictly higher than its floor):**

* The **same row** is reactivated (same `id`, same `uid`), `revision + 1`, a `revive` change row is written. An upsert with a sequence **below** the floor is ignored as stale and counted, never applied (no resurrection by an old delivery). An upsert **equal** to the floor is a `sequence_conflict` and the page is refused (a series tombstone's floor is always set by a delete, so an upsert at the floor is a different operation); only a strictly higher sequence revives.
* **Old overrides are not reactivated.** They stay `deleted`. The provider must resend any override it still wants.
* A resent override is applied only if its sequence is strictly higher than that override row's floor; it then **reactivates the same row** (`revive`, `deleted_by_cascade = false`), so `UNIQUE (series_id, recurrence_id)` holds and the override's identity is stable. A resend **below** the floor is ignored as stale and counted. A resend **equal** to the floor depends on the **floor origin**: for an override tombstoned by an explicit or unknown-entity **delete**, a delete item at the floor is a counted replay (same operation, `TOMBSTONE_HASH`) and an upsert at the floor is a `sequence_conflict`; for a **cascade-tombstoned** override (`deleted_by_cascade = true`) the floor is the sequence of its own last upsert and the tombstone keeps no content or hash that could prove a resend identical, so **any** item at that floor, upsert or delete, is a `sequence_conflict`. In every case a `sequence_conflict` refuses the whole page (fail closed). No replay rule is added for cascade tombstones and no content is retained to enable one. **Consequence (disclosed in section 14, spike question in section 17):** a provider that resends an unchanged override (same `SEQUENCE`) after its series was deleted and revived blocks the page until it sends a strictly higher sequence. This relies on providers increasing `SEQUENCE` when a UID is reused; a provider that resets sequences on re-creation would see overrides ignored, which is the safe direction and is a spike question (settled as O4, section 14).
* An override arriving while its series is `deleted` (stored, or deleted in the same page) is **superseded**: counted, written as nothing, never blocking (section 7.3.1 Step 3). `override_orphan` is reserved for a series that is unknown everywhere.
* **Unknown-entity deletion** creates a tombstone with a floor, one `delete` row and counts toward the total limits (section 7.3.1).
* **A floor-raising delete is not a new deletion.** A delete with a sequence strictly above the floor of an entity that is already `deleted` advances only the floor (`sequence`), writes the net `delete` change row, and, for a cascade-origin override tombstone, changes the floor origin (`deleted_by_cascade = false`). It **preserves the original `deleted_at`**: the entity was deleted once, at the time recorded, and a later provider delete does not move that time. `deleted_at` is assigned only when an entity becomes `deleted` (explicit delete, unknown-entity tombstone creation, or cascade) and is cleared only by a revive, so `deleted_at` stays set exactly when `state = 'deleted'` (section 6.3).

**Explicit override delete:** the override becomes `deleted` (not by cascade); the instance **reverts to the generated instance**; it is not cancelled. Cancellation is an `active` override with `status = 'cancelled'`.

**Occurrence identities** are identical before deletion and after revival (section 5.6); no occurrence is returned while the series is deleted.

### 6.8 Transactional allocation of `calendar_changes.seq`

* A page is applied by exactly one writer: owner, source and sync-state rows are locked in that order, so `calendar_sync_state.applied_seq` is a **transactionally protected counter**. New sequence numbers are `applied_seq + 1 ... applied_seq + n`, assigned in the deterministic total order of section 7.3.1 (so the assignment is independent of the order in which items arrived in the page), and `applied_seq` is set to the last one in the same transaction. A rollback discards both the rows and the counter update, so numbers are gapless.
* The insert trigger on `calendar_changes` independently requires `NEW.seq = COALESCE(max(seq), 0) + 1` for the source (taking the source row `FOR UPDATE` first), so even a buggy writer cannot create a gap or a duplicate; `UNIQUE (source_id, seq)` is the final backstop.
* `max(seq)` is never used by the application to allocate (that would race); only the locked counter is.

### 6.9 Forgetting scrub and retention of `provider_ref`

In the same transaction as the source's `forgotten` transition:

* series and overrides become `forgotten`; every content column, `uid` and `rule`/`exdates`/`rdates` become NULL;
* every `calendar_changes.snapshot` becomes NULL (the only permitted update);
* `calendar_sync_state` becomes **exactly the terminal state** of section 6.5 (status `blocked`, reason `source_forgotten`, cursor, claim token, claim expiry, `blocked_detail` and `next_attempt_at` all NULL, `applied_seq` unchanged);
* **`provider_ref` is set to NULL** (the only permitted update of the link row). The link row itself is **retained** as the immutable exclusivity marker and as the parent of retained history; the opaque handle is not needed for it, and removing it data-minimizes the fixture reference. The API never returns `provider_ref` for a forgotten source. (Settled as O5 in section 14; retaining it was the rejected alternative.)
* Change rows are retained (counts, operations, sequences, timestamps, hashes) and contain no event content or identifiers after the scrub.

The deferred trigger of section 6.6 enforces this scrub at commit.

## 7. Provider interface, synthetic provider and synchronization

### 7.1 Interface and `ChangePage` contract (`calendar_provider.py`)

```python
class CalendarProvider(Protocol):
    def changes(self, since: str | None, limit: int) -> ChangePage: ...

@dataclass(frozen=True)
class ChangePage:
    items: tuple[ProviderItem, ...]   # at most `limit`, at most 64 KiB serialized
    next_cursor: str                  # opaque, non-empty, at most 512 chars
    has_more: bool
```

`ProviderItem` is an upsert or an explicit delete of a series or an override, with `uid`, `recurrence_id`, `sequence`, and for upserts a body in RFC 5545 terms (RRULE, `EXDATE` and `RDATE` value strings go through the section 5.7 parser). There is **no create, update or delete-event method on the provider**; a static test asserts that the protocol and the synthetic class define only read methods and import no network, socket or HTTP library. Errors are typed: `ProviderUnavailable`, `ProviderTimeout`, `InvalidCursor`, `CursorExpired`, `PageTooLarge`, `MalformedItem`.

The cursor is **opaque**: the application only ever compares it for equality with the cursor it sent or stored and never assumes an ordering. `since = None` means "from the beginning" and must never raise `InvalidCursor`.

**Cursor progress semantics (every combination is defined; unspecified combinations do not exist).** In this table `since` is the **fetch argument of that page**: the stored cursor, or `None` for the first page of an explicit resync.

| `items` | `has_more` | `next_cursor` vs `since` | Behaviour |
|---|---|---|---|
| any | any | empty or over 512 chars | page refused, `blocked` / `cursor_malformed` |
| non-empty | false | equal | **refused, `blocked` / `cursor_no_progress`**: applying and not advancing would re-fetch the same items every pass |
| non-empty | true | equal | **refused, `blocked` / `cursor_no_progress`** |
| non-empty | true or false | different | applied; cursor advanced in the same transaction; if `has_more`, the worker starts the next page with a fresh T1 (section 7.3 item 5; counted against the 10-page budget) |
| empty | **true** | **equal** | **refused, `blocked` / `cursor_no_progress`**: a provider claiming more data without moving must fail closed, never consume the page budget repeatedly |
| empty | true | different | allowed (a provider skipping filtered changes); no change rows; cursor advanced; counted against the page budget |
| empty | false | different | allowed; cursor advanced with zero changes (the guard requires `applied_seq == max(seq)`, which holds); status `ok` |
| empty | false | equal | **caught up**: status `ok`, `last_success_at` advanced by the section 6.5 expression, no change rows, cursor unchanged |

* **Repeated pages.** A page whose items were all applied before is accepted as a no-op: every item is a replay (counted as `replayed` in the page summary, never silently), and the cursor rules above still apply. Equality with the current cursor is the only loop detector available for opaque cursors; an A to B to A cursor loop is **not** detectable in general and is bounded only by the page budget and by idempotent apply (stated limitation).
* **Dependency order (provider contract, B3).** A provider **must** deliver a series in the same page as, or in an earlier page than, any override of that series, and must never deliver an override of a series it has not yet delivered. This is a documented guarantee of the synthetic provider (enforced by its writer, section 7.2) and a stated requirement on any future adapter (an adapter may reorder within one fetched page but never across pages). Within one page, order is irrelevant (section 7.3.1). If the contract is violated the result is `override_orphan`: the page is refused whole, data and cursor are unchanged, and the source is `blocked` (section 7.3.2). The recovery path is explicit and never skips the blocked item: the owner (in dev/test) or the harness corrects the provider side so that the missing parent precedes the override, then retries with `sync`; if the provider cannot reorder, the source stays visibly blocked, and a bounded pending-dependency mechanism is out of scope and listed as a future design question.
* **Invalid cursor** (`InvalidCursor`: malformed or unknown to the provider) and **expired cursor** (`CursorExpired`: the provider no longer holds history that old) both end in `blocked` with `cursor_invalid` or `cursor_expired`. Neither retries on its own. Only an explicit owner request `sync {resync: true}` restarts from `since = None`; applying from the beginning is safe because apply is idempotent. **Resync changes only the fetch argument** to `since = None`: it does not null or otherwise change the **stored** cursor to start the fetch (the guard of section 6.5 would refuse that). The stored cursor changes only in the T2 worker transition, to the cursor of the page just applied; T2 compares against the stored cursor recorded in T1, never against the `since` argument (section 7.3). Deletions that happened while the cursor was lost are **not inferred** (limitation, spike question). `since = None` itself is never reported as invalid.

### 7.2 Synthetic provider (D10)

* Backing store: a **SQLite file** (WAL) with `events` and an ordered `changes` log (`change_id INTEGER PRIMARY KEY AUTOINCREMENT`), plus a `faults` script table. The cursor is the opaque string `v1:<change_id>`.
* Config-gated, default **off**; only allowed when `BUTLER_ENV` is dev or test, and the same gate applies to the `provider`, `sync` and `sync-status` routes (section 10), to link creation and to the worker, which refuses to start otherwise; the path comes from configuration and must resolve inside one configured fixture directory (no traversal, no symlink escape); `provider_ref` selects a file name inside it and is never a path.
* The application opens it **read-only** (`mode=ro` URI) and reads each page inside one read transaction, so a page is an atomic snapshot of the log.
* A separate **writer process** (test harness only, not shipped in the API) appends changes atomically and **refuses to append an override unless its series already exists earlier in the log (or earlier in the same page)**, so the synthetic provider honours the dependency-order contract by construction, at every page size including 1. A test-only `fault: override_before_series` bypasses that refusal to prove the blocked behaviour, and a test-only `replace_from(change_id, items)` operation rewrites the unapplied tail of the log to simulate the provider-side correction, after which a retry must succeed. Faults scripted by the writer: timeout N times, unavailable, partial page, duplicate delivery of an item, out-of-order items within a page, explicit delete, late update after delete, invalid cursor, oversize page, malformed item, unsupported rule.
* Because the store is a file, two genuine OS processes (writer, worker) and a worker that is killed and restarted observe the **same** provider state. This is what makes the restart tests honest; the in-memory double used for filing in #26 could not.

### 7.3 Synchronization state machine and transaction boundaries

The diagram below shows **one page**: each page of a pass is one complete T1, fetch, T2 (or T3) cycle (item 5).

```
never --claim--> [lease] --fetch--> [apply txn] --> ok            (cursor + applied_seq + changes in ONE txn)
                     |                  |--> blocked(reason)       (page refused whole; cursor unchanged)
                     |--> retry_wait (attempts+1, backoff) --> ... --> failed (attempts = 5)
```

1. **Claim transaction (T1).** T1 receives an **invocation-level `explicit` flag**: true only when the call comes from the owner `sync` route (dev/test, section 10), false for the worker. It is **never persisted**, and no other caller can set it. Lock owner, then source, then `calendar_sync_state` (same order as #26). **An unexpired lease is a no-op for every caller**: the lease is never overridden, an explicit call returns the current status and changes nothing, and no claim is set. Otherwise a **scheduled worker** (`explicit = false`) skips the source if `status in (failed, blocked)` or `next_attempt_at` is in the future; an **explicit** call skips for neither. In the same transaction an explicit call of a `failed` source sets `attempts = 0` before the attempt; an explicit call of a `retry_wait` or `blocked` source leaves `attempts` unchanged. The **stored cursor is never changed by requesting a sync**, and `status` and `next_attempt_at` are not changed by T1 either (they change only in T2 or T3). The full policy is the table after item 7. Set `claim_token`, `claim_expires_at`. Read the **stored `cursor`** under the lock and keep it with the claim (held by the worker next to its `claim_token`; no column is added). Commit. The claim commits **before** any provider call.
2. **Fetch (no locks, no open transaction).** `changes(since, limit)` with a bounded timeout, where `since` is the stored cursor recorded in T1, or `None` for an explicit resync (section 7.1). **The fetch timeout must be strictly shorter than the claim lease** (120 s by default), so a healthy fetch cannot outlive its own claim; the worker refuses to start with a configuration where it is not, and tests that shorten the lease shorten the timeout below it.
3. **Apply transaction (T2).** Lock owner, source, sync state again. Verify: our `claim_token` still holds, the source is active (not forgotten), the link exists, and the stored `cursor` still equals the **stored cursor recorded in T1** (compare-and-swap against the stored value, not against the `since` argument used for the fetch, which differs on a resync). Validate the **whole** page as in section 7.3.1; on any violation roll back and run T3 as `blocked`. Apply in the deterministic write order of section 7.3.1. Allocate `calendar_changes.seq` from the locked `applied_seq` counter (section 6.8) and insert the rows (system actor, NULL). Update `cursor`, `applied_seq`, `last_success_at` (the one expression of section 6.5), clear the claim. On success T2 also sets `status = 'ok'`, `attempts = 0` and sets `next_attempt_at`, `last_error_code`, `blocked_reason` and `blocked_detail` to NULL, so that the next page's T1 cannot skip the source because of retry or blocked state left over from an earlier failure. Commit once.
4. **Failure transaction (T3).** Provider timeout/unavailable: `attempts + 1` (counted normally whether the attempt was scheduled or explicit; a failed explicit attempt **never resets the backoff schedule**), backoff chosen by the new attempt count: **30 s after the first failure, 2 min after the second, 10 min after the third, 1 h after the fourth**, giving `next_attempt_at` and status `retry_wait`. **The fifth failure** (`attempts = 5`) sets the status to `failed` and `next_attempt_at` to NULL; no fifth interval exists, so there is no further automatic attempt, and a `failed` source is attempted again only by an explicit owner sync. Clear the claim. Blocked codes never retry on their own.
5. **A pass** is a bounded loop. For each of at most 10 pages it runs one complete cycle: T1 (new `claim_token`, record the stored cursor), fetch, then T2 (apply, set the cursor, release the claim) or T3. **No claim is held between pages**: T2 releases it, as the cursor guard of section 6.5 requires on every cursor change, so the next page starts with a fresh T1 that reads the stored cursor committed by the previous T2. A pass is therefore **not an exclusive reservation**: another worker or an owner sync may claim between pages, which is safe because T1 reads the stored cursor under the lock and T2 compares against it (a lost race fails the compare-and-swap or finds the lease held, and applies nothing). A pass ends for a source when a page reports `has_more = false` (section 7.1), after 10 pages, or on a T3 outcome (`blocked`, `retry_wait` or `failed`), whichever comes first. A pass handles at most 100 sources; the page and source counts are explicit limits. An explicit `resync` applies to the pass's **first fetch only** (`since = None`); later pages continue from the stored cursor committed by the previous T2, so a pass interrupted after its first page simply continues forward from there on the next pass.
6. **Item ordering rules** are defined once, in section 7.3.1 (per-entity reduction table, floors, revival, cascades, net change rows).
7. **Cursor progress and invalid or expired cursors** are fully specified in section 7.1 (including `cursor_no_progress`, `cursor_invalid`, `cursor_expired`, `cursor_malformed`). Deletions that happened while a cursor was lost are not inferred; this is a stated limitation and a spike question.

**Owner sync versus the scheduled worker (decided policy).** An explicit owner sync initiates an attempt immediately instead of doing nothing because an automatic retry is scheduled; the lease remains the only concurrency safeguard.

| Situation | Explicit owner sync (`explicit = true`) | Scheduled worker (`explicit = false`) |
|---|---|---|
| `retry_wait`, future `next_attempt_at` | Bypasses backoff and attempts; `attempts` is **preserved** (unchanged before the attempt) | Skips |
| `failed` (`next_attempt_at` NULL) | Sets `attempts = 0` in T1, then attempts | Skips |
| `blocked` | Permits one explicit retry (7.3.2 item 3); `attempts` unchanged | Skips |
| Unexpired lease | **No-op**: returns the current status, changes nothing, never overrides the lease | Skips |
| Successful attempt | T2 resets the retry and blocked state (item 3) | Same |
| Failed attempt (provider timeout or unavailable) | Normal T3: `attempts + 1`, backoff by the new count, never a reset of the schedule; fifth failure: `failed`, `next_attempt_at = NULL` | Same |

The stored cursor is not changed merely because an explicit sync was requested, and `resync` still only changes the fetch argument (section 7.1). A consequence to state plainly: an explicit attempt on a `failed` source that crashes after its T1 (P1) leaves the source `failed` with `attempts = 0` until the next explicit sync, because T1 does not change `status`; the scheduled worker never retries a `failed` source. Repeated manual failures count: five consecutive failures, scheduled or explicit, leave the source `failed` and visibly so.

### 7.3.1 Page application algorithm (validation, per-entity reduction, final-state resolution, deterministic write order, limits)

This is **one algorithm**. Series, overrides, tombstones, cascades and limits interact only through the steps below, so no interaction is left to implementation discretion. All of it runs inside the apply transaction after the locks are taken and **before any row is written**; any violation rolls the whole page back (all or nothing).

**Step 1: shape and grammar.** Every item against sections 5.3, 5.7 and 5.8; page size and item count; cursor progress (section 7.1).

**Step 2: group and reduce each entity against its stored state (pure, in memory).**

* Group items by entity key: a series by `uid`; an override by `(series uid, recurrence_id)`. Within a group sort ascending by `sequence`. Two items of one entity with the same `sequence` must have the same operation and content hash (they collapse to one) or the page is `sequence_conflict`.
* Simulate each item, in that order, against the entity's state, updating the simulated state after each item (so later items compare against earlier ones in the same page):

  | Simulated state | Item with sequence `q` | Upsert | Delete |
  |---|---|---|---|
  | **absent** (never seen) | any `q` | creates it active | **creates a tombstone with floor `q`** (unknown-entity deletion, below) |
  | **active**, sequence `s` | `q < s` | stale: ignored, counted `ignored_stale` | stale |
  | | `q = s` | same operation and hash: replay, counted `replayed`; otherwise `sequence_conflict` | same |
  | | `q > s` | updates it | deletes it (a series delete cascades, below) |
  | **deleted**, floor `f` | `q < f` | stale | stale |
  | | `q = f` | `sequence_conflict` | **delete-origin tombstone:** counted replay; **cascade-origin override tombstone:** `sequence_conflict` |
  | | `q > f` | **revives** the same row | raises the floor to `q` (no cascade; an override tombstone then has a delete-origin floor, `deleted_by_cascade = false`); **`deleted_at` is preserved** (not a new deletion, section 6.7) |

  **Floor origin.** A tombstone's floor is set either by a **delete** (explicit delete, or unknown-entity deletion; every series tombstone is of this kind) or, for an override only, by the **cascade** of its series' delete, in which case the floor is the sequence of the override's own last **upsert** (`deleted_by_cascade = true`, section 6.7). At `q = f`: an upsert is always a `sequence_conflict`; a delete is a counted replay against a delete-origin floor (same operation and `TOMBSTONE_HASH`) but a `sequence_conflict` against a cascade-origin floor, because the tombstone retains no content or hash that could prove an identical resend. This keeps the existing fail-closed behaviour: no replay rule is added for cascade tombstones and no content is retained to allow one. The consequence (a provider resending an unchanged override after series deletion and revival blocks the page until it sends a higher sequence) is a disclosed limitation (section 14) and a provider-spike question (section 17).

* Reduce the simulation to one **net result per entity**: its final state and the single change row it writes. Replays and stale items write nothing.

  | State at start of page | State at end | Net operation (one `calendar_changes` row) |
  |---|---|---|
  | absent | active | `upsert` |
  | absent | deleted | `delete` (tombstone creation) |
  | active | active | `upsert`; for a **series** whose reduction passed through a delete (delete then higher upsert in the page) the net operation is `revive` with the cascade already performed |
  | active | deleted | `delete` |
  | deleted | active | `revive` |
  | deleted | deleted | `delete` (floor raised; the row's original `deleted_at` is kept) |
  | any | unchanged (all items stale or replay) | no row |

  The row's `sequence` is the highest applied sequence and its `content_hash` is that of the final content (`TOMBSTONE_HASH` for a net `delete`, section 6.4). Two delete items of one entity with the same sequence are always the same operation and hash, so they collapse as replays. **Intermediate versions delivered inside one page are not stored as separate rows**: the change log records the net transition of stored state per entity per page, which is what the page's atomic apply makes observable. A cascade is part of the series' own net delete or net `revive`: `cascade_count` is the number of overrides that were `active` at the moment of the delete and are tombstoned (`deleted_by_cascade = true`); it counts only overrides that existed, never superseded items (Step 3).

**Unknown-entity deletion (explicit).** A delete for an entity the source has never seen **creates a tombstone** (`state = 'deleted'`, `uid` or `recurrence_id`, floor = the delete's sequence, `deleted_at`), writes **one `delete` change row** (`cascade_count = 0`), and counts toward the **total** limits (400 series per source, 200 overrides per series) and the change-log limit, but **not** toward the active limits. Purpose: a later upsert **below** the floor is ignored as stale, an upsert **at** the floor is a `sequence_conflict`, and a later upsert with a strictly higher sequence revives the same row. An override delete is resolved by the **final state of its series** (Step 3): if the series ends **active**, the override tombstone is created under it (floor = the delete's sequence); if the series ends **deleted** (in the page or already stored), the override delete is **superseded**, creates **no tombstone** and moves no floor (the series' cascade owns the outcome); if the series is unknown everywhere, the page is `override_orphan`.

**Step 3: resolve overrides against their series' final state.** After all series are reduced, each override group is resolved by the **final state of its series after the page**, never by item position:

| Series final state | Override items |
|---|---|
| **active** | reduced as in Step 2 against the override's stored state **after the series' cascade** (an override tombstoned by a delete earlier in the same reduction can be revived only by a strictly higher sequence, as in section 6.7). Every override that ends active, including `cancelled` ones, is checked for membership of the series' **final instance set** (section 5.8); a non-member is `override_unmatched` and the page is refused. **Untouched stored overrides are revalidated too:** when the series' net result is an `upsert` whose content hash differs from the stored one (its rule, `EXDATE`, `RDATE`, `DTSTART` or zone changed), every stored `active` override of that series that the page does not mention is also checked against the final instance set, after the page's own override items have been reduced (an override the same page **explicitly deletes with a strictly higher sequence than the stored one** is no longer active after reduction and is not checked: this is the only O3 exception; a **stale** delete is ignored and an **equal-sequence** delete is a `sequence_conflict` (Step 2), so neither removes the override from the check and neither resolves the mismatch; an override the page **updates**, including setting it `cancelled`, stays active, keeps the same `recurrence_id` and is checked like any other, so an update never resolves a mismatch). A stored override that no longer matches refuses the whole page atomically with `override_unmatched`; the diagnosis is `entity = 'override'`, `sequence` = the stored override's sequence, `uid_digest` of the series, `recurrence_digest` of the override and `item_index: null` (the stored override is not an item of the page), and when several overrides are unmatched, the reported one is the first by the **total order `(series uid, recurrence_id)`**, both compared as UTF-8 byte strings, over **all candidate overrides, whether delivered in the page or only stored** (section 7.3.2); never a silent drop or a cascade. At most 100 active overrides are checked, so the work is bounded. A series `revive` has no stored active overrides (6.7) and an `upsert` with an unchanged hash needs no recheck |
| **deleted** (deleted in this page, or a tombstone already stored) | **superseded**: the series' cascade owns the outcome. The items write no override row and create no override state; they are counted as `superseded_by_delete` in the page summary. This is not an error and does not block the page: a valid provider history of "override updated, then series deleted" is accepted whichever order the two arrive in |
| **unknown everywhere** (not stored, not in the page) | `override_orphan` (the provider dependency-order contract was violated; section 7.1) |

Consequence, stated as a limitation: **every override item received while its series is deleted** (deleted in the page, or already stored as deleted) is superseded and **moves no floor**. That covers an override first delivered in such a page, which leaves no floor, and also later updates and deletes of an override that is already stored: a cascade tombstone keeps its floor and its `deleted_by_cascade = true` origin unchanged. If the series is later revived, an old override resent with a sequence above the unmoved floor is accepted as new, and a resend exactly at that floor is a `sequence_conflict` (section 6.7). This is the same completeness class as O4 and a spike question.

**Step 4: deterministic total order of writes.** The net results are written in a total order that depends only on entity content, never on page position, so **any permutation of the same items produces the same rows and the same `calendar_changes.seq` assignment**. There is at most one row per entity, so entity keys are the tie-breaker and no ties remain:

| Phase | Net results written | Sort key (ascending) |
|---|---|---|
| 1 | series net `delete` (each performs its cascade) | `uid` |
| 2 | series net `upsert` and `revive` (a `revive` performs its cascade when it is written) | `uid` |
| 3 | override net `delete` (including tombstone creation) | series `uid`, `recurrence_id` |
| 4 | override net `upsert` and `revive` | series `uid`, `recurrence_id` |

`uid` and `recurrence_id` are compared as **UTF-8 byte strings** (equal to code-point order; never database collation or locale; any database ordering used in tests is `COLLATE "C"`). **Series rows are always written before the override rows that reference them** (an override tombstone or upsert under a series created in the same page needs its parent row first, because of the composite foreign key). Within each kind, deletions precede upserts, and cascades are performed before the overrides they affect are re-evaluated, so row counts only grow after the deletions and the trigger backstops of section 6 never fire on a state the page does not end in. A test creates a new series and an override tombstone under it in one page to prove the parent-first order.

**Step 5: limits against the final state of the complete page.** Before writing, compute purely: final active series and override counts, final total rows including tombstones, the number of change rows (one per entity with a net result), and the final instance sets for override matching. A page that deletes N series and adds N at the limit passes; a page whose final state exceeds any limit is refused whole with the specific code (`series_limit`, `override_limit`, `tombstone_limit`, `change_log_full`, `page_too_large`). Intermediate states are never evaluated.

**Step 6: cursor.** The cursor and `applied_seq` change in the same transaction and only after all of the above succeeded.

**Item reordering versus page reordering (distinct guarantees).**

* *Item reordering* (the same items in a different order inside one page, including an override listed before its series or before its series' delete): the result is **identical, including change rows and `seq`**, because grouping, reduction, final-state resolution and the write order are functions of item content only.
* *Page reordering or out-of-order delivery across pages* (a later page applied before an earlier one, or an older page replayed after a newer one): for the **same entity**, sequences make the result converge (stale items are ignored, never applied). For a **cross-entity dependency split across pages** (an override arriving before its series was ever delivered), the result is `override_orphan`, a blocked page, never a partial apply. The cursor protocol prevents the application itself from reordering pages.

### 7.3.2 Blocked-source guarantees (O1 conditions)

Whole-page blocking is accepted (O1). Four guarantees are explicit and tested:

1. **Stable, sanitized diagnosis.** A blocked source exposes `blocked_reason` (a stable code from the canonical list of section 7.3.3) and `blocked_detail`, a JSON object whose **six keys are always all present**: a value that does not apply is JSON `null`, **never an omitted key** (known-answer tests compare the exact object with all six keys). It is built by one shared function; the database only bounds its size (section 6.5).

   | Key | Value | JSON `null` when |
   |---|---|---|
   | `code` | the `blocked_reason` | never |
   | `entity` | `page`, `series` or `override` | never |
   | `item_index` | zero-based index in the page of the offending item (for several items of one entity, the item with the **highest sequence among the entity's items**, including items that were rejected) | `entity = 'page'`, or the offending override is a **stored** override that is not an item of the page (the untouched-override recheck of section 7.3.1 Step 3) |
   | `sequence` | the offending item's sequence; for a stored override found unmatched, **that stored override's own sequence** (not the incoming series sequence) | `entity = 'page'`, or the item has no usable sequence (`item_malformed`) |
   | `uid_digest` | digest of the **series** `uid` (for an override, its series' `uid`) | `entity = 'page'`, or the item has no `uid` or one that cannot be used as a string (`item_malformed`) |
   | `recurrence_digest` | digest of the override's `recurrence_id` | `entity` is not `override`, or the override item has no `recurrence_id` or one that cannot be canonicalized (`override_type_mismatch`, `item_malformed`, `zone_*`) |

   **Digest definition (identical wherever referenced).** Each digest is the **first 12 characters of the lowercase hexadecimal SHA-256** of a **length-prefixed UTF-8 encoding**: for each field in order, a 4-byte big-endian unsigned length of the field's UTF-8 bytes followed by those bytes, so no two different field tuples can produce the same input (raw concatenation is never used). Fields: `uid_digest` encodes (`source_id`, series `uid`); `recurrence_digest` encodes (`source_id`, series `uid`, `recurrence_id`). `source_id` is its lowercase hyphenated textual UUID; `recurrence_id` is its canonical wall-time identity string of section 5.6 (`YYYY-MM-DDTHH:MM:SS`, or `YYYY-MM-DD` for all-day); `uid` is used exactly as stored (case-sensitive, no normalization). The same function is used by every producer, and a test asserts fixed known-answer vectors for both digests.

   **Selection when several candidates qualify.** For `override_unmatched`, the **candidates** are every override that ends active and is not a member of its series' final instance set, **whether it was delivered in the page or is only stored** (the untouched-override recheck). The reported candidate is the first by the **total order `(series uid, recurrence_id)`**, `uid` compared first and `recurrence_id` second, **both as UTF-8 byte strings** (never a database collation, never page position, and never a page-item ordering rule), so two different series that share a `recurrence_id` are still ordered and the detail is identical on every retry and under every permutation of the page. When a page is refused for more than one reason, the first violated step of 7.3.1 is reported; for errors attached to page items in Steps 1 and 2 it is the first item in the deterministic entity order of Step 4 (limit errors of Step 5 are page-level and name no item), and for Step 3 it is the first candidate by the order above.

   That is enough for the owner to find the item in a fixture they control. It contains no title, time, location or other event content, and no raw `uid` or `recurrence_id`: only the two 12-character digests. For page-level codes (limits, cursor progress) `entity` is `page` and no item is named. **Malformed items:** when an item is malformed or its `uid` or `recurrence_id` is missing or cannot be canonicalized, the corresponding digest is `null` (a raw, non-canonical value is never hashed or echoed) and `item_index` identifies the offending page item, so the owner can still locate it in a fixture they control.
2. **Last-known data stays visible.** A blocked source keeps serving its last successfully applied data, labelled with `as_of = last_success_at` and state `blocked` (section 8.3). Blocking never hides or deletes applied data and never presents it as current.
3. **Explicit retry only.** A blocked source is skipped by the worker and does not retry by itself; the owner's explicit `sync` request (dev/test, section 10) retries once, and `sync {resync: true}` additionally restarts from `since = None`. A retry of an uncorrected page blocks again with the same code and no side effects.
4. **Atomic failure and later success.** A failed page changes neither applied data nor the cursor nor `applied_seq` (asserted by comparing a full table digest before and after), and after the provider-side correction a retry applies the corrected page and advances the cursor.

### 7.3.3 Canonical code lists

`calendar_sync_state.blocked_reason` and `last_error_code` are constrained to these lists, which live in **one shared module** that the migration check, the application and the tests all import (a test asserts that the database check and the module agree exactly).

**`blocked_reason` (a page or source is refused; no automatic retry):**
* Grammar and rules (5.3, 5.7, 5.8): `range_thisandfuture`, `freq_unsupported`, `by_rule_unsupported`, `by_day_ordinal`, `by_month_day_negative`, `rscale_unsupported`, `count_until_both`, `count_limit`, `interval_limit`, `rule_part_unknown`, `rule_part_duplicate`, `rdate_period`, `utc_value_ambiguous`, `rrule_syntax`, `by_list_duplicate`, `by_day_freq_unsupported`, `by_rule_freq_mismatch`, `until_before_start`, `until_type_mismatch`, `dtstart_not_synchronized`, `exdate_type_mismatch`, `rdate_type_mismatch`, `override_type_mismatch`, `zone_mismatch`, `zone_floating`, `zone_unknown`, `rule_too_large`, `exdate_limit`, `rdate_limit`, `item_malformed`.
* Relations: `override_unmatched`, `override_orphan`, `sequence_conflict`.
* Limits: `series_limit`, `override_limit`, `tombstone_limit`, `change_log_full`, `page_too_large`.
* Cursor: `cursor_malformed`, `cursor_no_progress`, `cursor_invalid`, `cursor_expired`.
* Terminal: `source_forgotten`.

**`last_error_code` (retryable provider failures):** `provider_unavailable`, `provider_timeout`.

Page summaries (not blocking, never silent) report the counters `replayed`, `ignored_stale` and `superseded_by_delete`.

### 7.4 Crash and recovery behaviour

| Point | Meaning | Expected result |
|---|---|---|
| P0 | before T1 | nothing changed; next pass starts normally |
| P1 | after T1 commit, before fetch | lease held until expiry; after expiry a new worker re-fetches from the stored cursor; nothing applied |
| P2 | after fetch, before T2 | page lost, never applied; re-fetched after lease expiry |
| P3 | inside T2, before commit | whole transaction rolled back; cursor and data unchanged; lease expiry then re-fetch |
| P4 | after T2 commit | page applied; cursor advanced atomically; next worker starts from the new cursor; re-fetching the same page would be a no-op |
| P5 | between pages (after a T2 commit, before the next T1) | no claim is held between pages, so there is no lease to wait for; the next worker starts immediately from the last committed cursor |
| P6 | during T3 | rolled back; same as P1/P2 |

Every point is tested twice: as an aborted task in-process, and as a **real subprocess exit** (`os._exit`, precedent `test_actual_process_exit_rolls_back_before_retry`) followed by a **fresh process** that recovers, with the SQLite provider shared on disk. After every recovery the invariants are asserted: cursor never ahead of applied changes, no duplicate change rows, expansion identical to before the crash.

### 7.5 Guarantee statement (documented in spec 070)

**Guaranteed:** a page may be fetched more than once; applying the same item more than once has the same database effect as applying it once (per-item sequence rule plus the unique change index); the stored cursor never points past changes that are not committed; a refused page leaves data and cursor unchanged; a forgotten source is never revived.

**Not guaranteed:** that the provider is queried only once per change (this is at-least-once fetch, **not exactly-once**); that a provider honours cursors or keeps tombstones; recovery of deletions missed while a cursor was lost; ordering between independent entities across pages; freshness better than the stale threshold; recall of anything outside the database (there is no external effect in this batch, and external writes are disabled).

## 8. Briefing v2 contract

Same route (`POST /api/v1/calendars/briefing`), same authorization. The request gains an optional `horizon_days` (1 to 7; omitted keeps today's one-day response shape, so existing clients are unaffected). When present the response has `schema_version: 2` and keeps every v1 field.

### 8.1 Horizon and placement

* `day` is the first display day, `horizon_days` consecutive display days in the display zone, DST-aware. Events are grouped by display day.
* All-day events are placed by date (section 3); timed events by instant. A timed event crossing midnight appears on each day it overlaps, flagged `continues`.
* Recurring instances come from the expander on read (never stored). Each carries `recurring: true`, `exception: modified|none`, and its stable `id`.
* Cancelled instances are not shown as events but are counted in `cancelled_count`.

### 8.2 Per-source state (an enum, never a boolean)

`available`, `stale` (last success older than 24 h), `unavailable` (retrying, failed or provider down; last good data shown and labelled), `blocked` (with `blocked_reason` and the sanitized `blocked_detail`; the last good data stays visible), `unknown_coverage` (never synchronized, or requested range outside covered range), `limit_reached` (section 9).

### 8.3 Uncertainty handling

* **One source down never hides the others;** each source carries its own state and its own events.
* A stale, unavailable **or blocked** source's events are labelled with `as_of` (the last successful sync time) and the source state; they are not dropped and not presented as current. A blocked source additionally shows its `blocked_reason` and sanitized `blocked_detail`.
* Coverage unknown is stated as unknown. No inference of missing events and **no inferred household needs or next actions** (D11).
* Possible duplicates across sources (same title and overlapping interval) are flagged `possible_duplicate_of`; they are **never merged or removed**.
* Overlap flags remain timed-only.

### 8.4 Limits in the briefing

See section 9: `truncated`, `omitted_at_least` and per-section counts replace the current silent slices (G13).

## 9. Numerical limits and exact behaviour when reached

No limit ever drops data without an explicit state. "Refuse" always means: nothing in the page or request is applied, the cursor does not move, a stable code is returned or recorded, and the source shows the state. **Sync limits are evaluated against the final state of the complete page** (section 7.3.1), never item by item, so a page that deletes and adds the same number of entities at a limit is accepted.

| Limit | Value | Behaviour when exceeded |
|---|---|---|
| Active series per source | 200 | Page refused whole; sync `blocked` / `series_limit`; source `limit_reached`; existing data untouched |
| Total series rows per source (active and tombstones) | 400 | Page refused whole; `blocked` / `tombstone_limit` |
| Active overrides per series | 100 | Page refused whole; `blocked` / `override_limit` |
| Total override rows per series (active and tombstones) | 200 | Page refused whole; `blocked` / `tombstone_limit` |
| Change rows per source | 5,000 | Rows the page would write (**one per entity with a net result**; replays, stale and superseded items write none; a series delete writes one row regardless of cascaded overrides; an unknown-entity deletion writes one) are added to the current count; if the total would exceed 5,000 the page is refused whole, `blocked` / `change_log_full`. **No compaction in this batch** (retention design deferred), so this is a deliberate hard stall that is visible, not a silent loss; recorded as a limitation |
| Expanded occurrences per series per query | 366, counted **after** exclusions and overrides | The count is of occurrences that would actually be emitted for the window: generated and `RDATE` instances **after** `EXDATE` removal and after skipping nonexistent generated times, with overrides applied (a moved instance counts at its new time, in or out of the window as appropriate; a cancelled instance is not emitted and does not count, it is reported in `cancelled_count`). The earliest 366 by effective start are returned with `truncated: true`, the series id in `truncated_series`, an `occurrences_at_least` count and the section state `partial`; never presented as complete |
| Candidate wall times scanned per series per call (work bound, before any filtering) | 5,000 | Exceeding it returns `truncated` with reason `scan_limit` for that series; never a silent short result |
| Query / briefing horizon | 400 days (query), 7 days (briefing) | Request refused 422 `horizon_exceeded` |
| Briefing events | 100 | `events_truncated: true` with `omitted_at_least` (counted up to cap + 1); today's silent slice is replaced |
| Briefing sources / tasks | 25 / 25 | `sources_truncated` / `tasks_truncated` flags with counts |
| Provider page | 100 items, 64 KiB, cursor 512 chars | Page refused `blocked` / `page_too_large` (items or bytes), `cursor_malformed` (cursor) |
| Cursor that does not progress | equal to the requested cursor with `has_more` or with items | Refused `blocked` / `cursor_no_progress`; costs one fetch, never the page budget (section 7.1) |
| Rule JSON / exdates / rdates | 4 KiB / 100 / 100 | Page refused with `rule_too_large`, `exdate_limit`, `rdate_limit` |
| COUNT / INTERVAL | 1,000 / 999 | Rejected (section 5.3) |
| Retry attempts | 5 | The fifth failure sets `failed` with `next_attempt_at = NULL`; stays failed until an explicit owner `sync` (which resets `attempts` to 0 and attempts immediately, section 7.3) |
| Lease | 120 s | After expiry another worker may claim |
| Pages per pass / sources per pass | 10 / 100 | The pass stops; remaining work is picked up next pass (not a loss: cursor is durable) |
| Sources per owner | 10 (existing) | Existing 429 `calendar.source_limit` |

## 10. API and UI changes

Additive; existing routes, payloads and tests unchanged. All owner-only, all scope-checked, and a foreign, forgotten or unknown source returns 404 with the same body as an unknown id. **The `provider`, `sync` and `sync-status` routes exist only in dev and test**: outside those environments (or without the synthetic store configured) they are not registered and return the same 404 as an unknown route; link creation and the worker are gated the same way. Query and briefing remain available in every environment and serve whatever data exists.

* `POST /api/v1/calendars/{id}/provider` declares provider mode for a never-imported source.
* `POST /api/v1/calendars/{id}/sync` requests **one bounded pass** (up to 10 pages, section 7.3 item 5), **never repeated passes**; body `{resync?: bool}`; returns the sync status. It is the **only caller that sets T1's `explicit` flag** (not persisted). It bypasses backoff and the failed/blocked skip but never an unexpired lease: if the lease is held it changes nothing and returns the current status (policy table, section 7.3).
* `POST /api/v1/calendars/{id}/sync-status` returns status, cursor age, attempts, `next_attempt_at`, `blocked_reason`, the sanitized `blocked_detail` (the six-key object of section 7.3.2: digests only, never a raw `uid` or `recurrence_id`), last error code, counts (`ignored_stale`). No provider payloads.
* `POST /api/v1/calendars/query` additionally returns expanded provider-source occurrences with `truncated`/`truncated_series`.
* `POST /api/v1/calendars/briefing`: section 8.
* Frontend: `CalendarPanel` shows mode, sync status and honest stale/unknown/blocked wording and a "Sync now" action for synthetic sources; `DailyOverviewPanel`/`daily-overview.ts` consume the server briefing for calendar data, show per-source state, recurring and exception markers, possible-duplicate notes, and truncation notices. Frontend tests cover every state and the all-day cross-zone case.

## 11. Security, ownership, permissions, privacy and forgetting

* Every route and the worker re-check owner and scope under lock; the worker acts as a **NULL system actor** in `calendar_changes` and never impersonates the owner.
* Runtime grants: SELECT/INSERT/UPDATE on series, overrides and sync state; SELECT/INSERT and `UPDATE (snapshot)` on changes; SELECT/INSERT on links. No DELETE or TRUNCATE anywhere. Tested with the restricted role.
* The provider contract has no write method; the provider module imports no network library (static test). No credential exists in this batch.
* Synthetic store path: configured directory only, `provider_ref` pattern-restricted, opened read-only; traversal and symlink escape tests.
* **Ownership integrity is enforced by the database** (composite foreign key chain, section 6.0), not only by routes; the restricted runtime role cannot create a cross-owner, cross-scope or cross-source relationship in any of the five tables.
* **Forgetting** extends the existing `forget` and is specified in section 6.9: in the same transaction as the source's transition to `forgotten`, series and overrides become `forgotten` with content and `uid` NULL, `calendar_changes.snapshot` becomes NULL, `calendar_sync_state` is cleared and terminal, and `provider_ref` is set to NULL; a deferred trigger refuses a commit that did not scrub (section 6.6). No change can be appended afterwards; the worker refuses a forgotten source; an apply racing a forget is serialized by the owner then source lock order. A provider re-sending a forgotten uid is refused. Export of a forgotten source returns nothing.
* Audit entries record counts and codes, not event content.
* Privacy of the briefing: event titles are returned only to the owner of the source within the requested scope, as today.

## 12. Migration, downgrade, upgrade and restore

* Migration `0035_calendar_provider_sync` after `0034`: five new tables with the composite foreign keys of section 6.0, their triggers (limits, identity immutability, override-under-active-series, change log guard and gapless `seq`, sync-state guard, link rules), indexes and grants. Additive DDL on `calendar_sources` only: the unique index `uq_calendar_source_identity (id, owner_id, scope_key)`, the `butler_calendar_provider_exclusive` trigger and the deferred scrub-completeness trigger. No existing column, function or trigger is modified.
* Existing sources and manual-import behaviour and tests are unchanged; nothing is backfilled.
* **Downgrade** drops the five tables, their functions, the two additive triggers and the additive unique index. All provider-mode data is lost by design; this is stated in the migration docstring and in spec 070. Legacy sources are untouched.
* Verification: single linear head; fresh upgrade; downgrade to 0034 then re-upgrade; upgrade over a database already holding suite data; the repository's round-trip (down to 0012 and back).
* Restore: `scripts/test-db-restore.sh` head becomes `0035_calendar_provider_sync`; a new `scripts/calendar-provider-restore-fixtures.py` seeds, before the dump, a provider-mode source with a recurring series, an override, a cascade-tombstoned override, a deleted series, a revived series, a claimed sync state with an unexpired lease and a non-trivial cursor, and checks after a strict restore: the rows, the guards, the exclusivity trigger, the cursor invariant (`applied_seq` equals max change `seq`) and that the lease eventually expires and a worker recovers. Run on PostgreSQL 16 locally (emulation) and PostgreSQL 17 on hosted CI; the Docker script itself cannot run in this sandbox and that is stated.

## 13. Test strategy

Every rejection test asserts the **specific** stable code or refusal, so a rejection for another reason cannot pass (the #25 lesson).

**Recurrence and time**
* Golden cases per supported construct, derived from RFC text; DAILY, WEEKLY with `BYDAY` and `WKST`, MONTHLY by month-day, YEARLY, interval, COUNT, UNTIL (date and UTC instant), EXDATE, RDATE, override moved, override cancelled, override reverted (deleted), and a series change that would orphan an existing override, which must be **refused as a whole page with `override_unmatched`** (data and cursor unchanged), and succeeds only when the same page also **deletes** that override with a strictly higher sequence (an update of it, or a stale or equal-sequence delete, is still refused).
* Property tests: deterministic, sorted, bounded; same input gives the same ids on every run.
* DST matrix: Europe/Paris 2026-03-29 and 2026-10-25, America/New_York 2026-03-08 and 2026-11-01, Australia/Lord_Howe (30-minute shift), Pacific/Apia (date line). Each covers a **nonexistent time**, an **ambiguous time**, a series crossing the change, an all-day event and duration across the change.
* Skipped nonexistent dates (31 Feb, 29 Feb).
* All-day events across display zones (event zone ahead, behind, equal; multi-day; boundary), including the G1 regression and the multi-day horizon.
* Static tests: `dateutil` imported only in `calendar_recurrence.py`; `rrulestr`/`parser`/`tz` never imported; provider module imports no network library.
* **Section 5.4 examples as executable tests:** weekly 02:30 Europe/Paris, `COUNT=4`, `DTSTART` 2026-03-15: exactly the instances 15 Mar, 22 Mar, 5 Apr, 12 Apr with instants 01:30Z, 01:30Z, 00:30Z, 00:30Z, and **no** 29 Mar instance; a test that fails if the skipped instance is shifted to 03:30 or consumes `COUNT`. Explicit `DTSTART` in the gap (counts as 1, pre-gap offset). Ambiguous generated time takes the first occurrence. `RDATE` in the gap uses the §3.3.5 interpretation and is not counted. Modified override into the gap uses §3.3.5. Override naming the skipped instance is `override_unmatched`.
* Same matrix for America/New_York 2026-03-08 and 2026-11-01, Australia/Lord_Howe and Pacific/Apia; `COUNT` with skipped instances; `UNTIL` as date and as UTC instant around a skipped instance; 31 February and 29 February skipped without consuming `COUNT`; `EXDATE` of `DTSTART` still counts as instance 1.
* Set algebra: `EXDATE` wins over `RDATE` and the rule; `RDATE` duplicating a generated instance yields one instance; an unmatched `EXDATE` is accepted and counted; `RDATE` never consumes `COUNT`; type matching (DATE versus DATE-TIME, UTC `Z` converted to series-zone wall, other `TZID` rejected).
* Strict grammar: a table-driven suite (one case per rule of 5.7: case-insensitivity, duplicates, empty parts, whitespace, non-ASCII, leading zeros, signs, list limits and duplicates, `UNTIL` forms, floating `UNTIL`, `dtstart_not_synchronized`), round-trip `parse(serialize(rule)) == rule`, and a bounded fuzz asserting only typed errors and bounded time.
* Occurrence ids identical across expansion, restart, resync, and across series deletion and revival.
* Every rejection in section 5.3, each with its code.

**Sync and recovery**
* Idempotent apply: replay, reorder, duplicate, partial page, invalid cursor, oversize page, late update after delete, revival with higher sequence, equal-sequence conflict, stale (lower sequence) counted.
* Cursor invariant after every injected fault and after every crash point P0 to P6, as aborted task **and** as real subprocess exit with a fresh recovering process on the shared SQLite provider; cursor durability across the restart asserted from the database.
* Bounded retry and backoff (30 s, 2 min, 10 min, 1 h), `failed` at the fifth failure with `next_attempt_at = NULL`; an explicit owner sync of a `failed` source resets `attempts` to 0, while an explicit sync of a `retry_wait` or `blocked` source preserves them (policy table, section 7.3); `resync` changes only the fetch argument and has no effect on the attempt-reset policy; stale after 24 h by an injected application clock; unknown coverage.
* **Monotonic `last_success_at` (G2):** two consecutive applies within the same clock tick still strictly advance it (including the caught-up and empty-page paths); a simulated backwards database clock step (a row whose `last_success_at` is ahead of `clock_timestamp()`) still advances by exactly the one-microsecond term and the apply succeeds; the displayed age is clamped to 0 and never negative; with a forward-drifted value the source is labelled fresh for at most the drift and never stale earlier.
* **Resync and compare-and-swap (N9):** an explicit resync fetches with `since = None` while the stored cursor stays non-NULL and unchanged until T2; T1 records the stored cursor and T2 compares against it, so a resync apply succeeds and sets the stored cursor to the applied page's cursor; a concurrent change of the stored cursor between T1 and T2 makes the compare-and-swap fail and the page is not applied; a direct SQL statement that nulls or changes the cursor outside the T2 transition is refused by the guard (section 6.5).
* **Multi-page pass (F4, F5, F6).** With more than 10 pages available, a pass applies **exactly 10 pages** and stops with `has_more` still true; the stored cursor is the cursor of page 10 and the next pass resumes from it. Each page uses a **distinct `claim_token`**, `claim_token` is NULL after every T2 and **no claim is held between pages** (asserted from the database between pages). After a success T2 has reset `status = 'ok'`, `attempts = 0` and NULLed `next_attempt_at`, `last_error_code`, `blocked_reason` and `blocked_detail`, so a source that was in `retry_wait` or `blocked` before an explicit request is not skipped by the next page's T1. **Interleaving:** a second worker (and an owner sync) claiming between pages applies the next page, with no duplicate and no lost change, and the first worker's later T1 reads the new stored cursor; a T2 whose recorded stored cursor no longer matches applies nothing (compare-and-swap). **Crash:** P5 (between pages) as an aborted task and as a real process exit resumes from the last committed cursor with **no lease wait**, while P1 after the next T1 waits for lease expiry. **Resync:** an explicit resync fetches `since = None` for the first page only; later pages continue from the stored cursor, and a pass interrupted after its first page continues forward on the next pass. A T3 outcome (`blocked`, `retry_wait`, `failed`) ends the pass for that source without fetching further pages, and a page with `has_more = false` ends the pass even when fewer than 10 pages were applied (asserted with a log of 3 pages: exactly 3 fetches, none after the third).
* **Owner sync policy (B-1, O-3, O-4).** With a controllable clock and the synthetic provider, one test per row of the policy table in 7.3, each run for the owner route and for the scheduled worker: (a) `retry_wait` with a future `next_attempt_at`: the worker skips and the fetch count stays 0; the explicit sync fetches once, `attempts` is unchanged before the attempt, and on success T2 resets `status`, `attempts`, `next_attempt_at` and the error fields; (b) `failed` (`next_attempt_at` NULL): the worker skips; the explicit sync sets `attempts = 0` in T1 and attempts; a further failure gives `attempts = 1` and the 30 s backoff, not a continuation of the old count; (c) `blocked`: the worker skips; the explicit sync retries once, an uncorrected provider blocks again identically (section 7.3.2) and a corrected one applies; (d) unexpired lease held by another claimant: both callers are a no-op that returns the current status, with no claim change, no fetch, and `attempts`, `status` and cursor unchanged; after the lease expires an explicit sync claims normally; (e) failed attempts, scheduled or explicit, at each count, never a reset of the schedule: from `attempts = 2` a failure gives `attempts = 3` and a 10 min backoff (count 3); from `attempts = 3` it gives `attempts = 4` and a 1 h backoff (count 4); from `attempts = 4` it gives `attempts = 5`, status `failed` and `next_attempt_at = NULL` (count 5, no interval); five consecutive failures, any mix of scheduled and explicit, end `failed`; (f) the stored cursor is byte-identical before and after a request that fetched nothing (lease held); (g) the flag is not a column or a persisted value anywhere (schema inspection), and no route other than the owner `sync` route can set it; (h) one owner sync applies at most 10 pages and returns, and a second pass requires a second request; (i) the worker refuses to start with a fetch timeout that is not strictly shorter than the claim lease, and with the shortened test lease the fetch of a slow synthetic provider times out before the lease expires.
* Compose one-shot: the `calendar_worker` container runs one pass against the disposable database and exits.
* Concurrency: two workers plus an API sync racing one source; one claimant, no deadlock; bounded repeats (stated as not a soak test); apply racing forget.

**Query lookback (B1).** A timed series whose instance starts 30 days before the query window with a 31-day duration appears (it overlaps the first day); maximum duration at the exact boundary: an instance starting exactly 31 days before the query start (ending exactly at the query start) is **not** returned (end exclusive), one second later it is; the same pair for an all-day series with `duration_days = 31`; a lookback case across a DST change; an instance moved by an override into the window from outside it, and one moved out; the offset-change sweep over all IANA zones; an assertion that the expander uses the shared duration constants.

**UTC values in a fold (B2).** `2026-10-25T00:30:00Z` accepted and identified as wall `2026-10-25T02:30:00`; `2026-10-25T01:30:00Z` rejected `utc_value_ambiguous`; an unambiguous UTC value (`2026-10-25T10:00:00Z`) accepted; a UTC value just after the spring gap (`2026-03-29T01:30:00Z`, wall 03:30) accepted; the same four cases for `RDATE`, `EXDATE` and `RECURRENCE-ID`; two distinct instants never collapse into one occurrence; local-form and UTC-form values denoting the same instant with different identities stay two occurrences with distinct ids.

**Dependency order and blocked sources (B3, O1).** At page size 1 and at larger sizes the synthetic writer produces series before overrides and every page applies; with the `override_before_series` fault the override page is refused `override_orphan`, `blocked_detail` names the entity, item index, sequence, `uid_digest` and `recurrence_digest` (section 7.3.2) and contains no event content and no raw `uid` or `recurrence_id`, the last good data is still served with `as_of` and state `blocked`, a table digest before and after shows no data, cursor or `applied_seq` change, the worker does not retry by itself, an uncorrected explicit retry blocks again identically, and after `replace_from` corrects the log a retry applies the page and advances the cursor. An override and its series in the same page in either item order applies identically.

**Dev/test gating (O2).** In a production-configured app the `provider`, `sync` and `sync-status` routes are unavailable (same 404 as an unknown route), link creation is refused and the worker refuses to start; the same routes work in test configuration.

**Page application algorithm (7.3.1).** Every case below is run for **all permutations of a small page and a seeded set of random shuffles of a larger page**, and for each permutation the resulting `calendar_changes` rows are compared **row by row** on `(seq, entity, series uid, recurrence_id, operation, sequence, content_hash, cascade_count)` (excluding only random row ids, `sync_run_id` and timestamps), together with the final series, override and sync-state rows (for every override row the comparison includes `state`, `sequence`, `deleted_by_cascade`, `deleted_at` and the content columns). **`deleted_at` semantics in the comparison (N-2):** (a) `deleted_at IS NULL` is compared for every row in every permutation and must be true exactly when `state = 'active'`; (b) for a row the page did not change, and for a row whose only change is a **floor-raising delete** (N-3), `deleted_at` is compared **by exact value** and must equal the value stored before the page; (c) for a row that **becomes** deleted in the page (explicit delete, tombstone creation, cascade) the value is database-assigned, so it is asserted only to be non-NULL and within the transaction's time bounds as measured by the test, and is **not** compared by value across permutations (the rows of one page that become deleted share one transaction, and the test asserts they do not precede the transaction start). Cases:
* independent series upserts, deletions with cascades, override upserts and deletions;
* **same-entity mixes**: upsert then delete (higher), delete then higher upsert (net `revive` with cascade), upsert 3 and delete 5 of one override where the override never existed (net tombstone, no active override), three versions of one entity, stale and replayed items inside the page, equal sequence with different content (`sequence_conflict`);
* **unknown-entity deletion**: series tombstone creation (floor, one `delete` row, counts toward the 400 total and not the 200 active), a later stale upsert ignored, a later higher upsert revives the same row; override tombstone under a stored series that ends active; override delete under a series whose final state is `deleted` (stored, or deleted in the same page, both item orders) is superseded: no tombstone, no floor, counted `superseded_by_delete` (N-1); override delete under a series that is unknown everywhere is `override_orphan`; limits at the boundary;
* **override with series delete in one page, both input orders**: override upsert plus series delete where the override was previously active (net: series `delete` with `cascade_count = 1`, override superseded, no override row, final override tombstoned by cascade) and where it never existed (net: series `delete`, `superseded_by_delete = 1`, no override row, no floor); the page is **not** blocked, the cursor advances, and the exact rows, `seq` allocation, cascade effects and final state are asserted;
* **Floor boundary (R3):** for a series tombstone and for a delete-origin override tombstone (explicit or unknown-entity delete; the cascade-origin case is the next bullet), an upsert at floor minus one is ignored and counted (`ignored_stale`), an upsert **at** the floor is `sequence_conflict` with the page refused and data, cursor and `applied_seq` unchanged, a delete **at** the floor of a delete-origin tombstone is a counted replay, and an upsert at floor plus one revives the same row; a series revival does not reactivate its overrides.
* **Cascade-tombstone floor (B1):** an override that was active with sequence `s` is tombstoned by its series' delete (floor `s`, `deleted_by_cascade = true`); then, in separate cases and after the series is revived: an **unchanged resend** of that override at `s` is `sequence_conflict` (page refused, table digest, `applied_seq` and cursor unchanged, source `blocked`); a **delete item at `s`** is also `sequence_conflict` (not a replay); a resend at `s - 1` is ignored and counted; a resend at `s + 1` revives the same row with `deleted_by_cascade = false`. Contrast case in the same test: an override tombstoned by an explicit delete at `d` treats a delete at `d` as a counted replay and an upsert at `d` as `sequence_conflict`. A floor-raising delete at `q > f` of a cascade tombstone makes the floor delete-origin (`deleted_by_cascade = false`) and a later delete at `q` is then a replay.
* **State transitions of the cascade tombstone (F2).** Each case asserts the **resulting rows**, not only the response: the override's `state`, `sequence` (the floor), `deleted_by_cascade` and `deleted_at`, and the `calendar_changes` rows (operation, sequence, `content_hash`, `cascade_count`), in every permutation of the page: (1) the cascade leaves the override `deleted`, floor `s`, flag true and writes **no** override change row (the series row carries `cascade_count`); (2) an ignored stale item at `s - 1` leaves the override row identical (floor and flag unchanged) and counts `ignored_stale`; (3) a refused item at `s` leaves every table unchanged; (4) a delete at `q > s` leaves the override `deleted`, floor `q`, flag false, **`deleted_at` exactly equal to its value before the page** (the cascade's original deletion time, asserted by value; a floor-raising delete is not a new deletion, N-3), with exactly one `delete` row (sequence `q`, `TOMBSTONE_HASH`, `cascade_count = 0`); (5) the multi-version page `[upsert s+1, upsert s+2, delete s+3]` on a cascade tombstone nets to `delete`: floor `s+3`, flag false, exactly one row with sequence `s+3` and no rows for the intermediate versions; (6) `[upsert s+1, delete s+2, upsert s+3]` nets to `revive`: state `active`, sequence `s+3`, flag false, one row; (7) `[upsert s+1, delete s+1]` is `sequence_conflict` with nothing applied; (8) a stale or equal item never changes the flag, and the flag never changes without the floor or the state changing in the same statement.
* series deleted then revived in one page with stored active overrides (overrides tombstoned by the cascade, `cascade_count` equals their number) and an override resend with a higher sequence (revives) versus **below** the floor (ignored as stale and counted) versus **equal** to the floor (`sequence_conflict`, page refused, nothing applied);
* **Untouched stored overrides and same-page interactions (G3, R1, C7, C8).** A series `upsert` whose changed rule leaves a stored active override unmatched:
  * page does not mention the override: refused whole, `override_unmatched`;
  * same page also **deletes** that override with a strictly higher sequence than the stored one: **accepted** (series updated, override tombstoned with its own `delete` row, no mismatch);
  * same page carries a **stale** delete of that override (sequence below the stored one): the delete is ignored, the override stays active and the page is refused `override_unmatched`; an **equal-sequence** delete is refused `sequence_conflict` (N1);
  * same page also **updates** that override (any content, including `cancelled`): **refused `override_unmatched`**, because the override stays active with the same `recurrence_id`;
  * the delete and update cases each with **both incoming item orders**, and every permutation of the small page, comparing rows as in the algorithm test above;
  * a series `upsert` with an unchanged hash does not recheck; a `revive` has no stored active overrides, and a resent override is judged against the revived series' final set;
  * several unmatched overrides (B2): the one first by the total order `(series uid, recurrence_id)` in UTF-8 bytes is reported, identically on every retry and under every permutation. Cases: **two different series that share the same `recurrence_id`** (the series with the lower `uid` bytes wins, asserted on the exact `blocked_detail`); a mix of a **stored-only** candidate and a **delivered** candidate (ordering is by the composite key, not by origin or page position); uids and recurrence ids that differ only in case and in non-ASCII bytes (byte order, not collation).
  **Atomicity on every refusal above (C7):** a full table digest (series, overrides, sync state, change rows) taken before and after is identical, `applied_seq` and `cursor` are unchanged, no `calendar_changes` row was added, and the source shows `blocked` / `override_unmatched` with last-known data still served.
* **`blocked_detail` (R2).** Known-answer vectors for `uid_digest` and `recurrence_digest` (length-prefixed encoding; a pair of field tuples that would collide under raw concatenation, such as uid `ab` with recurrence `c` versus uid `a` with recurrence `bc`, produces different digests); the `null` rules of the table in 7.3.2 asserted for each entity and code (page-level, series, override item, stored override with `item_index` `null`, malformed item with missing or non-canonicalizable `uid`, `recurrence_id` or `sequence`), with the **exact object compared, all six keys always present and `null` (never an omitted key)**; `null` handling is verified **at the application layer** (the shared builder), since the database check is only a size bound and is not claimed to validate keys or `null` semantics; the JSON contains no raw `uid`, `recurrence_id`, title or time (a scan over a fixture with distinctive values); the `sequence` of an unmatched stored override is the stored override's, not the series'; the detail is identical across retries.
* **Delete-row hash (G6, C9):** every `delete` row (explicit, unknown-entity tombstone, floor raise, cascade-owning series delete) carries `TOMBSTONE_HASH`; a test asserts the literal vector `136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01` for the UTF-8 string `butler.calendar.tombstone.v1`, and the permutation comparison includes the column.
* Uids that differ only in case, in Unicode normalization and in non-ASCII characters check ordering by UTF-8 bytes rather than database collation.

**Cursor progress.** Every row of the section 7.1 table as a test (including `cursor_no_progress` for an empty page with `has_more=true` and an unchanged cursor, which must not consume the 10-page budget more than once; empty page with an advanced cursor; empty page with an unchanged cursor as caught up; repeated pages as replays; `cursor_invalid`, `cursor_expired` and owner resync from `since=None`). Item reordering within a page converges to an identical result including change rows; page reordering converges for the same entity and gives `override_orphan` for a cross-entity split where the series was never delivered, never a partial apply.

**Series and override lifecycle.** Series delete cascades to overrides in one transaction with a single change row (`cascade_count`); tombstoned overrides do not count toward the 100-active limit but toward the 200-total limit; revival with a higher sequence reactivates the same series row and does **not** reactivate overrides; stale revival and stale override resend (sequence **below** the floor) are ignored and counted; an upsert or resend **equal** to a tombstone floor is `sequence_conflict` and refuses the page; a delete item equal to the floor of a delete-origin tombstone is a replay, while **any** item at the floor of a cascade tombstone is `sequence_conflict`; a resent override with a higher sequence reactivates the same row; an override whose series is deleted (stored or in the page) is superseded and counted, never blocking, while an override of a series unknown everywhere is `override_orphan`; explicit override delete reverts to the generated instance; an active override under a non-active series cannot be created or kept (direct SQL).

**Limits**
* **Final-state evaluation:** a page that deletes N series and adds N at the 200 limit is accepted; the same page with N+1 additions is refused whole with the cursor unchanged; a page that deletes and re-adds the same uid keeps one row. The 366-occurrence limit is tested with exclusions, `RDATE`, cancellations and overrides moving instances into and out of the window; the scan limit is tested with a series whose window contains no valid instances.
* Each limit in section 9 at limit minus one, at the limit and at limit plus one, asserting the explicit state, an unchanged cursor, and that nothing was silently dropped (counts equal before and after).

**Database ownership integrity (direct SQL as the restricted runtime role; each statement must be refused, asserting the specific constraint or trigger and that no row was written):**
* a link whose `owner_id` or `scope_key` differs from its source;
* a series with an owner or scope that differs from its source's, and a series on a manual-mode (unlinked) source;
* an override whose `source_id`, `owner_id` or `scope_key` differs from its series', or whose `series_id` belongs to another source;
* a change row whose series or override belongs to another source, owner or scope, with both or neither of `series_id`/`override_id`, with `entity` not matching, or with a non-NULL `actor_id`;
* a sync-state row whose owner or scope differs from its source's;
* an update that changes `source_id`, `owner_id`, `scope_key`, `series_id`, `recurrence_id`, `created_at` or `uid`;
* a gap or duplicate in `calendar_changes.seq`; a cursor change without the matching `applied_seq`;
* **a change to `cursor` alone while `applied_seq` already equals `MAX(calendar_changes.seq)`** (refused); a cursor change that advances `last_success_at` but does not release a held claim (refused); a cursor change that releases a claim but does not strictly advance `last_success_at` (refused); a decreasing `applied_seq` (refused); **`applied_seq` set above `MAX(calendar_changes.seq)`, and `applied_seq` increased without matching change rows (refused)**; **the forgetting transition**: accepted when the source reads as `forgotten` (as it does inside the forgetting transaction) and the row becomes exactly the terminal state of 6.5; refused when the source is still `active`, when `cursor` is set NULL outside it, when the terminal statement keeps a non-NULL cursor, changes `applied_seq` or `last_success_at`, or moves to another status, and every update of a terminal row refused; and the legitimate worker transition (release claim, advance `last_success_at`, matching `applied_seq`, new cursor) accepted. **Forgetting transition columns (G1, G7, C1, C10):** the terminal statement is accepted only with `revision + 1`, a non-decreasing `updated_at` and unchanged `attempts`, `last_attempt_at`, `last_success_at`, `last_error_code` and identity columns, and refused if any of them differs; it is refused when the source does not read as `forgotten`; an update of an already terminal row (including one whose source was forgotten in an earlier committed transaction) is refused **as an update of a terminal row**, asserting that constraint, not a transaction-identity check, which the guard does not perform; and a forget that commits without the terminal sync state is refused at commit. The tests assert that the guard is documented as a necessary-condition check: one test shows that a statement satisfying every condition with an arbitrary cursor value is **accepted**, so no stronger guarantee is claimed than the trigger provides.

**Exclusivity trigger (direct SQL):** legitimate forgetting succeeds; forgetting with `revision + 2`, with a decreasing `updated_at`, with non-NULL `data`, or with any identity column changed is refused; manual import, `unavailable` and any `data` change on a linked source are refused; any update after `forgotten` is refused; a forget that leaves an `active` series, an override, a snapshot, a `uid` or a `provider_ref` is refused at commit; an unlinked legacy source is unaffected (the existing 11 + 6 tests unchanged); linking after an import or after forgetting is refused.

**Security and privacy**
* Foreign owner, wrong scope, forgotten source, unknown id (identical 404 body), runtime role denied DELETE/TRUNCATE and out-of-contract UPDATE, history append-only with NULL-only redaction, no change after forgetting, resurrection refused, exclusivity trigger tested directly with raw SQL and via the API.

**Migration, restore, frontend, CI**
* Upgrade, downgrade, re-upgrade, round trip, strict restore fixture, frontend state tests, `ruff check`/`format`, unit suite, full integration suite on a **fresh** database, and the failing test IDs **compared as an exact list** against the baseline (the 75 known failures on `b1e716f`, rechecked against the then-current main). A failure is never called baseline without that identifier comparison. Hosted CI including the PostgreSQL 17 restore job.

## 14. Exclusions and remaining limitations

**Excluded from Batch 3:** any real account, credential, network client, CalDAV or ICS parser or provider activation; any external write, mirroring or event creation; inferred household needs and next actions; any model call; free/busy, travel time, scheduling advice; attendees, invitations, alarms, attachments; per-event forgetting; event notifications and reminders (next batch); unified attention inbox and approvals; infrastructure status; changes to the 068/069 workers (their process-restart retrofit is tracked **separately**); changes to routines' DST convention; compaction of the change log.

**Known limitations that remain:**
* ORG-01 and MVP-02 remain partial until a real-connector spike.
* The synthetic provider is more forgiving than any real provider.
* Deletions missed while a cursor was lost are not recovered (section 7.3).
* The 5,000-change limit stalls a source visibly with no compaction. The **tombstone totals** (400 series per source, 200 overrides per series) can stall a source the same way: tombstones are never removed in this batch, so a long-lived source that churns uids or recurrence ids eventually reaches `tombstone_limit` and stays blocked until a retention design (deferred) or a new source. This is visible (`blocked` / `tombstone_limit`), never a silent loss.
* **Unchanged override resend after series deletion and revival blocks the page.** A cascade-tombstoned override keeps as its floor the sequence of its own last upsert and no content or hash (6.7, 7.3.1 Step 2), so an identical resend at that sequence cannot be recognised as a replay and is a `sequence_conflict`. A provider that resends an unchanged override (same `SEQUENCE`) after its series was deleted and revived therefore blocks the page, visibly, until it sends a strictly higher sequence. This is the fail-closed direction, it is a provider-contract question, and it is a spike question (section 17, with O4); no replay rule or content retention is added in this batch.
* An unsupported construct blocks the whole page (O1).
* Concurrency tests are bounded, not a soak test; the Docker restore script is not run locally.
* The 75 sandbox integration failures remain undiagnosed and are compared by exact identifier, not assumed.
* `python-dateutil` is a new dependency; its behaviour on edge cases is covered by our own golden tests, not trusted.

**Design questions settled in review (12 Nov 2026).** None remains open for the proposal; each is revisited when a real provider is designed.

* **O1, settled:** a page with an unsupported or invalid item is blocked whole, with the four guarantees of section 7.3.2.
* **O2, settled (changed from the earlier default):** the owner `provider`, `sync` and `sync-status` routes are **dev/test only** (section 10), consistent with the synthetic provider (section 7.2).
* **O3, settled:** a series change that would orphan an existing override is refused as a whole page unless the same page explicitly deletes that override with a strictly higher sequence. An override update (including `cancelled`), a stale delete or an equal-sequence delete never resolves the mismatch, because the override keeps its `recurrence_id` and stays active.
* **O4, settled:** tombstone sequence floors are kept; after a delete and revive, overrides are not reactivated and a resend must carry a strictly higher sequence (an equal sequence is a `sequence_conflict`, including for an unchanged resend of a cascade-tombstoned override; see the limitation above). The completeness risk (a provider that resets `SEQUENCE`) is recorded and investigated in the real-provider spike.
* **O5, settled:** `provider_ref` is set to NULL on forgetting and the link row is retained.

Stated limitations (not open questions): every override item received while its series is deleted, first deliveries as well as later updates and deletes of already stored overrides, is superseded and moves no floor, so an old-incarnation override resent after a later revival with a sequence above the unmoved floor is accepted as new (same completeness class as O4; section 7.3.1); intermediate versions of one entity inside a single page are not stored as separate change rows; the database guard on `calendar_sync_state` checks necessary conditions only and cannot prove that a cursor value matches the committed changes; that guarantee rests on the worker protocol and the crash tests (section 6.5); cursor loops longer than one step (A to B to A) cannot be detected for opaque cursors and are bounded only by the page budget and idempotent apply; the dependency-order guarantee is a provider contract (guaranteed by construction for the synthetic provider, required of any future adapter), and a bounded pending-dependency mechanism for providers that cannot honour it is out of scope.

## 15. Implementation plan: seven commits and the audit gate

**PR A (docs only, proposal only):** contains **exactly one file**, `docs/BATCH3_CALENDAR_RECURRENCE_PROPOSAL.md`, branched from current `origin/main`. It does not touch ROADMAP, FEATURE_REGISTER, BACKLOG_STATUS, FEATURE_OVERVIEW, FEATURE_PROGRESS, FEATURE_DASHBOARD or the FILING_EXECUTION title; that refresh for #24 to #26 (G12) is part of commit 7 of PR B (or a separate docs-only change that needs its own authorization), together with tracking the 068/069 process-restart retrofit as a separate item.

**PR B (one draft PR, seven grouped commits, one push after local verification):**

1. All-day briefing fix with the cross-zone regression tests (G1).
2. `calendar_recurrence.py`, `calendar_provider.py`, the SQLite synthetic provider and its writer harness, `python-dateutil` pin; unit tests (recurrence, DST, rejection codes, static import tests).
3. Migration 0035, models, grants, system actor, triggers (including the exclusivity trigger) and migration tests. **MANDATORY AUDIT GATE: implementation stops immediately after this commit and waits for explicit approval. Nothing after it begins without that approval.** Report exact SHA and results; an independent review of the migration, triggers and grants happens here. **Mandatory audit item (F1, section 6.3):** the review explicitly decides whether the database enforces the coupling between a tombstone's floor and its `deleted_by_cascade` origin flag and records the decision and evidence; the accepted alternative is application-level enforcement recorded with its evidence and tests as defined in section 6.3 (O-1); if the invariant turns out to be enforced by neither the database nor such an accepted alternative, that is a blocker before the implementation can be declared complete.
4. `calendar_sync.py`, `calendar_worker.py`, claim, retry, limits, forgetting and export.
5. Briefing v2, API routes and frontend, including explicit truncation states.
6. PostgreSQL, real-process restart, concurrency and compose one-shot tests, restore fixture and script head bump.
7. Spec 070 (including the guarantee statement), limitations checklist and the status-document refresh for #24 to #26 (G12), including tracking the 068/069 process-restart retrofit as a separate item.

No push without your approval; the implementation PR is opened only after the agreed local implementation and verification stages are complete; nothing is merged by me.

## 16. Acceptance criteria for declaring Batch 3 complete

1. G1 regression passes and was shown failing before the fix.
2. Golden recurrence cases for every supported construct pass; every rejection in section 5.3 returns its specific code; no unsupported construct is approximated.
3. The DST matrix passes, including nonexistent and ambiguous times, all-day events across display zones, exceptions, cancellations and moved occurrences; occurrence ids are identical across expansion, restart and resynchronization.
4. Replaying pages and duplicating items converge. **Item reordering** within a page yields an identical result, **including identical `calendar_changes` rows and `seq` assignment** (deterministic total order and one net row per entity, section 7.3.1); **page reordering or out-of-order delivery** converges for the same entity by sequence and yields `override_orphan` (a blocked page, never a partial apply) for a cross-entity dependency split across pages. Late updates after deletion do not resurrect: an upsert **below** a tombstone's floor is ignored as stale and counted, an upsert **equal** to the floor is a `sequence_conflict` (page refused), and only an upsert with a strictly higher sequence revives the same row (6.7); overrides are not reactivated by a series revival.
5. For every crash point P0 to P6, both as aborted task and as real process exit with a fresh recovering process, the cursor is never ahead of committed changes and recovery produces the expected state.
6. Every limit in section 9 yields its explicit state with nothing silently omitted and the cursor unchanged; the briefing no longer slices silently.
7. Stale, failed, blocked and unknown states are honest; retries are bounded; last good data is labelled, not hidden; one failing source never hides another.
8. Ownership, scope, forgetting and resurrection tests pass; history is append-only with NULL-only redaction; runtime role has no DELETE or TRUNCATE.
9. Provider writes are impossible by construction (static test), no network import, synthetic store path contained, nothing real connected.
10. Mutual exclusivity of provider and manual modes is enforced by the database (direct SQL tests for legitimate forgetting, forbidden combined updates and updates after forgetting) and by the API. Ownership, scope and source consistency of all five tables is enforced by composite foreign keys and triggers, proven by direct SQL negative tests as the restricted runtime role.
10a. The section 5.4 worked examples pass as executable tests (the skipped generated instance does not consume `COUNT`); explicit, generated, `RDATE` and override instances each follow their own rule.
10b. Query expansion never misses an event that overlaps the window: the lookback derives from the shared maximum-duration constants and the exact 31-day boundary is tested (end exclusive); UTC-form recurrence values that cannot be represented losslessly are rejected, never collapsed.
10c. A blocked source (including cross-page `override_orphan`) exposes a sanitized, deterministic diagnosis (six keys, digests only, composite-ordered selection among several candidates), keeps serving labelled last-known data, never retries by itself, changes neither data nor cursor, and succeeds after a provider-side correction; the synthetic provider honours the dependency-order contract at page size 1.
10d. The provider, sync and sync-status routes, link creation and the worker are unavailable outside dev/test.
10e. Every `ChangePage` combination of section 7.1 behaves as specified; `cursor_no_progress` fails closed without repeatedly consuming the page budget; an explicit resync fetches from `since = None` without altering the stored cursor, and T2 compares against the stored cursor recorded in T1.
10f. Series deletion, revival and override lifecycle behave as in section 6.7, including limit accounting, unknown-entity deletion, the below-floor (ignored) versus equal-floor (`sequence_conflict`) distinction by floor origin (delete-origin versus cascade-origin) and the untouched-override revalidation of 7.3.1 Step 3 (only an applied delete with a strictly higher sequence resolves a mismatch).
10g. The page application algorithm of 7.3.1 gives identical change rows, `seq` assignment, cascades and final state for every permutation of a page, including same-entity mixes, and an override whose series is deleted in the same page never blocks the page.
10h. The sync-state guard accepts exactly the worker transition and the forgetting transition of 6.5 and refuses every other cursor change, including `applied_seq` above `MAX(seq)`; the doc claims no more than the trigger checks.
10i. A pass is one T1, fetch, T2 (or T3) cycle per page with no claim held between pages, at most 10 pages per pass, a successful T2 resets the retry and blocked state, and the multi-page test of section 13 passes (distinct claims, interleaving, P5 without lease wait, first-fetch-only resync).
10j. Floor-origin transitions of cascade tombstones are asserted on the resulting rows (floor, `deleted_by_cascade`, `deleted_at`, change rows), and the F1 audit item of section 6.3 was decided and recorded at the audit gate, either as database enforcement with direct-SQL negative tests or as the accepted application-level alternative with its recorded evidence and tests (O-1); an invariant enforced by neither is a blocker for completion.
10k. The owner-sync policy of section 7.3 holds exactly: the `explicit` flag is invocation-level, never persisted and settable only by the owner `sync` route; an explicit sync bypasses backoff and the failed/blocked skip but never an unexpired lease; `attempts` is reset to 0 only for a `failed` source and preserved for `retry_wait` and `blocked`; a failed explicit attempt counts normally and never resets the backoff schedule; the fifth failure sets `failed` with `next_attempt_at = NULL`; the stored cursor is unchanged by the request; one owner sync is one bounded pass; and the fetch timeout is strictly shorter than the claim lease.
11. Migration upgrade, downgrade, re-upgrade, round trip and strict restore pass on PostgreSQL 16 locally and 17 on hosted CI.
12. Full integration run on a fresh database: failing test IDs compared as an exact list to the baseline; no new failures; hosted CI green.
13. Spec 070 states the at-least-once fetch and idempotent apply guarantee and what is not guaranteed; docs and limitations updated; ORG-01 and MVP-02 still marked partial.
14. A draft PR with an independent self-audit exists; the audit gate after commit 3 was approved by you; nothing was merged without your approval.

## 17. Provider spike questions (unverified)

Everything in this section is derived from RFCs and common practice. **None of it has been observed against a real provider.** A real account needs your separate approval, a stated data flow and invented data only.

| Question | Why it matters | Contract impact |
|---|---|---|
| Sync token (RFC 6578) versus CTag/ETag; what happens on an invalid token | Cursor semantics, resync | Cursor type; whether deletions can be recovered |
| Identity by resource href versus UID; several VEVENTs in one resource; UID reuse | Occurrence identity | Id scheme, collisions |
| Which RRULE subset real calendars emit; COUNT versus UNTIL; EXDATE and RDATE usage | Expander coverage | Rule subset |
| `RECURRENCE-ID` with `RANGE=THISANDFUTURE`; orphan overrides | Excluded construct frequency | Whether exclusion is acceptable; O1 |
| VTIMEZONE, non-IANA TZIDs, floating times, gap and fold in the wild | Time correctness | Zone mapping and refusal rules |
| Deletion representation (removed resource, `STATUS:CANCELLED` or EXDATE); reliability of SEQUENCE and DTSTAMP | Deletion and ordering | Delete versus cancel model |
| Server-side `<expand>` (RFC 4791) as an oracle for our expander | Independent check | Test strategy |
| Paging, limits, timeouts, rate limits | Worker bounds | Page size, backoff |
| Shared, read-only and subscribed calendars; `CLASS:PRIVATE` | Scope and privacy | Ownership and visibility |
| Events longer than 31 days; open-ended recurrence | Window and horizon limits | Bounds |
| How providers represent generated instances that fall in a DST gap (omit, shift, or emit the shifted time as an override) | Whether §3.3.10 skipping matches observed data | D5, override handling |
| Whether `SEQUENCE` increases when a UID is deleted and re-created, and whether overrides are resent after revival | Revival and stale-floor rules; whether an unchanged override resend at its old sequence after series deletion and revival occurs in practice (a `sequence_conflict` block, 6.7 and 14) | O4 |
| `EXDATE` of the `DTSTART` instance, and `DTSTART` not matching `BYDAY` in the wild | Set algebra and `dtstart_not_synchronized` | Strictness of 5.7 |
| Whether real providers can deliver an override before its series across page or sync boundaries | Dependency-order contract (7.1); whether a pending-dependency design is needed | B3 |
| How UTC-form `RDATE`/`EXDATE` values appear for fold times | Whether `utc_value_ambiguous` rejections would occur in practice | 5.8 |
| Credential model and revocation | Security | Separate approval required |
