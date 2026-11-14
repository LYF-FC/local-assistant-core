# Spec 073 convergence

**Implemented on branch `codex/impl-073-work-status` from `main` at `2e04ff8` (merge of PR #36), under the owner's implementation authorization of 14 November 2026. Locally tested; not merged, not independently verified, not accepted.** Local evidence uses disposable PostgreSQL 16 databases and synthetic data only. Implementation, testing, verification and acceptance are separate facts; only implementation and local testing are claimed here. No OPS-09, OPS-10, Gate 10 or other gate, priority or acceptance status changes.

> **Merge record (added 14 November 2026, after the merge; the text above is retained as written at the time):** the implementation merged as [PR #37](https://github.com/LYF-FC/local-assistant-core/pull/37) (merge `4a7e624`, 14 November 2026). Pull-request-head CI passed on `2408a68` (run 43615751104) and the push to `main` at the merge commit `4a7e624` passed all six jobs (run 43624054196, attempt 1). Merging is integration only: it is not independent verification or owner acceptance, and no requirement, gate, count or priority changed because of it.

## Contract to code

| Contract (spec 073) | Code |
|---|---|
| E1–E8, verbatim worker conditions, cutoff `t` only | `backend/app/queue_eligibility.py` |
| Workers keep their selection at their own `now` | `jobs.claim`, `reminder_worker.candidates`, `notification_worker.enqueue_pass` / `candidates`, `filing_worker.candidates` |
| Observer at `now − 120 s` with observer-only guards; queue precedence; four queues; not-observed list | `operations.work_queries`, `observe_work`, `WORK_*` constants |
| Route, strict body, authority, timeouts, receipt check, audit-before-response, all-or-nothing | `operations.work_status`, `operations_routes.work_status` |
| D3: `operations.work_status` → `operations_read` | migration `0038_work_status_audit_category` |
| UI: explicit load, exact copy, expiry, hidden tab, session/grant change, late responses, no persistence | `frontend/src/WorkStatusSection.tsx`, `operations-api.ts` (`parseWorkStatus`, `readWorkStatus`), `OperationsPanel.tsx` |

## Worker selection preserved

- **Construction.** Each worker's WHERE clause is now a disjunction of the shared rules at its own single `now`; joins, `ORDER BY`, `LIMIT`, `FOR UPDATE` / `SKIP LOCKED` / `OF task_reminders` and `populate_existing` are untouched (see the diff of the four worker files). The rules take only `t`, contain no `updated_at` or `delivered_at` term, and the observer guards live only in `operations.work_queries`.
- **Compiled equality** (`tests/test_queue_eligibility.py`): each rule compiles to the original condition text; the notification rules equal the original `P AND (A OR B)` distributed.
- **Data equality** (`test_queue_eligibility_postgres.py`, test 12): frozen copies of the five pre-refactor selection statements and the refactored workers return identical **ordered** candidate IDs for limits 1, 2 and 100 at six clock values (0 s, 30 s, D − 1 s, D + 1 s, 10 min, 4 h) over a matrix with three owners: pending/unknown/in-flight/paused-disabled/paused-resumed deliveries, an enqueue-eligible reminder, future-dated `updated_at`/`delivered_at`/preference timestamps, absent preferences with a revision mismatch, an exhausted lease and a filing in flight. A non-vacuity check asserts each branch's row was selected at some time and the parked paused delivery never was.
- **No delay** (test 14): rows eligible at `T` and `T − 1 s` are selected and processed by one worker pass at `T` while the observer reports `none_observed`; worker selection is identical with the grace at 120 s and at 10 min.

## Mutation checks (each applied, tested, restored byte-identical)

| Mutant | Result |
|---|---|
| Drop reminder `r.updated_at` guard | 2 tests fail |
| Drop reminder preferences guard | 2 fail |
| Drop delivery `updated_at` guard | 1 fails (4b step 6.4) |
| Drop paused-row preferences guard | 1 fails (4b) |
| Drop enqueue `delivered_at` guard | 2 fail |
| Drop filing `updated_at` guard | 1 fails (added future-dated filing case) |
| Grace 120 s → 0 | 3 fail |
| Observer guard leaked into worker rule E3 | 4 fail (equivalence and compiled tests) |
| Paused exclusion dropped from E5 | 4 fail |
| UI: no abort and no generation/hidden guard | 2 component tests fail |
| UI: no hidden-tab clearing | 3 component tests fail |

## Test evidence (local)

- Backend `ruff check`, `ruff format --check`: clean. `bandit -r app ../pdf-worker -q`: no findings.
- Backend `pytest -m 'not integration'`: **1594 passed** (16 new: `test_operations_work_status.py`, `test_queue_eligibility.py`).
- PostgreSQL 16, CI-shaped (user `postgres`, fresh database, one process), `pytest -m integration --allow-hosts=127.0.0.1`: **1130 passed, 0 failed** (29 new: 25 in `test_work_status_postgres.py`, 4 in `test_queue_eligibility_postgres.py`; plus the taxonomy case and the `0038 ↔ 0037` round trip in `test_audit_summary_postgres.py`). The spec 073 tests each use a fresh copy of a migrated template database (`butler_test_ws_*`), dropped afterwards; none remained.
- Migration: upgrade 0037 → 0038, downgrade to 0037 (mapping removed), upgrade again (mapping restored); the round-trip test also verifies owner, `SECURITY DEFINER`, `search_path=pg_catalog`, runtime EXECUTE and no PUBLIC EXECUTE in both directions without re-granting. The existing spec 072 round trip to 0036 passes through 0038.
- Frontend `npm test`: **824 passed** (31 new parser tests); `npm run build` succeeded; `npm audit --audit-level=high`: 0 vulnerabilities; local opt-in browser specs: **36 passed** (9 new mocked component tests). These mocked tests are not hosted CI or real-stack evidence.
- Real-stack Playwright (`e2e/calendars.spec.ts`, new work-status test and finance-member denial) is **not run locally** (no container stack); its evidence is hosted CI only.
- `check_repository.py` passed; `build_feature_overview.py --check` verified (155 references); generated overview and dashboard unchanged.

## Deviations and adaptations (no contract change)

- The reminders API accepts only future schedules, so "a reminder created now with a past `scheduled_at`" (test 2) is shown by a reminder created now and due one second later, plus the future-dated `updated_at` arrangement; test 4a's backward-stepped write schedules just ahead of the stepped clock. Both exercise the same guards.
- Fixture arrangements that real write paths cannot produce use the owner connection with the table guard briefly disabled, exactly as existing worker tests do, and are labelled in the tests (4b step 6.4, future-dated timestamps, aged in-flight claims).
- Timeouts are applied with bound `set_config(..., true)` (transaction-local, equivalent to `SET LOCAL`).

## Not verified / remaining

- Hosted CI and real-stack Playwright on the PR head; independent review; owner acceptance. No real-host, restart or clock behaviour is claimed; synthetic process evidence (test 16) is synthetic-channel only.
- Pre-existing wording outside this change remains as it was: the `OPERATIONS_OVERVIEW.md` spec 072 heading ("branch engineering, unmerged"), the master snapshot header and `FEATURE_PROGRESS.json` at `5096134`, and the Operations overview's "Worker heartbeat / overdue work" component label (still `unknown`, now alongside the separate Work status view).
