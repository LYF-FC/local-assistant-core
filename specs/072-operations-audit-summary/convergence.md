# 072 convergence

**Implemented on the local branch `codex/spec-072-operations-audit-summary` (from `main` at `0fbea4e`); locally tested; not pushed, not independently verified, not merged, not accepted.** Evidence below was produced in a disposable local environment with synthetic data. Gate 10, OPS-09, OPS-10 and every other status, count and gate are unchanged; the first slice of OPS-10 exists, the rest is open. Implementation, testing, verification and acceptance are separate facts; only the first two are claimed, locally.

## Requirement mapping

| Contract item | Source | Evidence |
|---|---|---|
| Count-only projection; runtime role keeps no audit SELECT | spec §Scope, §Authorization; OPS-10 | `integration/test_audit_summary_postgres.py::test_function_guards_and_privileges` (runtime role cannot SELECT or count `audit_events`; append-only trigger still refuses delete) |
| Closed category/outcome catalogue, exact window, content-domain and lookalike exclusion | spec §Categories | `test_mapping_window_and_exclusions_are_exact` (20 mapped cases, 5 excluded types, outside-window and future rows; mutation check: adding `documents.` to the function makes it fail) |
| Function guards: definer, owner, fixed `search_path`, no PUBLIC execute, execute only for `butler_runtime`, single `(text, timestamptz, integer)` signature with no `uuid` overload, window only 24/168 | spec §Authorization | `test_function_guards_and_privileges` |
| Actor bound inside the database: another administrator's UUID, a stored hash, a decorated token and revoked/expired/idle/inactive/grant-revoked sessions are refused through the restricted runtime role; both administrators succeed with their own tokens | spec §Authorization | `test_actor_substitution_is_rejected_for_the_restricted_runtime_role` (mutation checks below) |
| Strict request, current authority, CSRF/Origin, revoked grant | spec §Authorization | `tests/test_operations_audit_summary.py` (SQLite) and `test_api_shape_denials_and_metadata_only_audit`, `test_revoked_grant_and_migration_round_trip` (PostgreSQL) |
| Exact response shape, totals equal column sums, no ids/actors/metadata | spec §Response | `test_api_shape_denials_and_metadata_only_audit`; client `parseAuditSummary` tests (16 rejection cases) |
| Audit of the read is metadata-only; failure withholds the response | spec §Audit | `test_audit_failure_withholds_the_summary` (induced insert failure on the runtime engine; no payload, no row) |
| No fabricated counts outside PostgreSQL | spec §Failure | `test_non_postgres_never_fabricates_counts_and_does_not_audit_success` |
| Migration round trip | spec §Migration | `test_revoked_grant_and_migration_round_trip` (downgrade to 0036 drops the function, upgrade restores it); migration-head assertions moved to 0037 in `test_calendar_schema.py` and `scripts/test-db-restore.sh` |
| Client parsing, explicit load, clearing, no persistence | spec §UI | `operations-api.test.ts` (58 passed); the section's clearing, late-response and retry behaviour is covered by the mocked component spec `frontend/browser/audit-summary.spec.ts` (9 tests, harness `test-harness/audit.tsx`); the real-stack spec below is separate and not run |

## Pre-push review remediation (local)

### 1. SECURITY DEFINER actor binding: a real defect, fixed

**Finding.** As first committed (`bb20110`), the function took `p_actor uuid` and checked only that this id was an active user with `technical_admin`. Every application user connects as the same `butler_runtime` role, and the function had no trusted identity inside the transaction, so a runtime-role caller could invoke it with *another* technical administrator's valid UUID and pass the check. Normal API behaviour (the route passes the authenticated user's own id) did not prove binding, and the old test only covered an actor *without* the grant. The database-side identity the route trusts is the live session: `identity.resolve` matches `AuthSession.token_hash = sha256(token)` and requires it unrevoked, unexpired, within the 30-minute idle limit, with an active user.

**Fix (no broad grant, no audit-table read).** Migration 0037 (still unpublished, so edited in place; the signature is the only thing that changed) now defines `butler_audit_summary(p_token text, p_end timestamptz, p_hours integer)`. The route passes the request's own session token (a bound parameter). The function hashes it with the same digest, looks up an unrevoked, unexpired, non-idle session of an active user who currently holds `technical_admin`, and otherwise raises `42501`. A token length outside 40 to 128 characters is refused. `runtime_role.configure` grants EXECUTE on the new signature only; no `uuid` overload exists. Ownership, `SECURITY DEFINER`, `search_path = pg_catalog`, `REVOKE ALL ... FROM PUBLIC`, and the downgrade (drops the new signature) were rechecked by the guards and round-trip tests.

**Tests.** `test_actor_substitution_is_rejected_for_the_restricted_runtime_role` runs on the restricted role with two real administrators: positive controls for both; a call with administrator B's UUID is refused (no such function); a stored `token_hash` used as a token is refused; decorated and truncated tokens are refused; B's session is then revoked, expired, idled, B deactivated and B's grant revoked, each refused, while A's own valid session is unaffected and A's revoked grant is refused even when B is valid. Mutation checks against the migration (each applied, re-migrated, tested, restored byte-identical): dropping the `revoked_at` predicate, the idle predicate, the `is_active` predicate or the scope predicate each made the substitution test fail (the scope mutant also failed the guards test).

**Residual limit, stated.** The runtime role can INSERT and UPDATE `auth_sessions`, so code already running as the runtime role with arbitrary SQL could create a session row for an administrator and use its token. That is pre-existing (it can already forge sessions for every route) and yields counts only; the function cannot close it. A live token is a bound parameter and could appear in PostgreSQL statement logs if parameter logging is enabled, the same exposure as the session lookup that precedes it. Neither is claimed solved.

### 2. Integration failures under the full suite

- **`test_installation_postgres.py::test_two_actual_configuration_databases_...`** asserts `settings.postgres_user == "postgres"` (it creates and drops databases, so it needs the superuser). Hosted CI sets `BUTLER_POSTGRES_USER: postgres` in `.github/workflows/ci.yml`; my earlier local environment used a different superuser name, so this was an environment incompatibility present before this branch, not a defect. With the local cluster configured like CI (user `postgres`, fresh database) it passes.
- **`test_calendars_postgres.py::test_session_expiry_after_actual_row_wait[briefing]`.** The test holds a `FOR UPDATE` lock on the calendar row, starts the request on a thread, waits (polling `pg_stat_activity` for a `Lock` waiter whose query matches `%calendar_sources%FOR %`, up to 5 s), then moves the clock past session expiry inside the locked transaction and expects 401 after release. It failed once while a second integration process was running against the same database, with "Calendar request did not reach actual row wait" (the 5 s wait for the lock waiter expired). Findings: (a) the same failure plus ten more reappeared in a deliberately re-created two-processes-one-database situation (my own mistake: two full runs started against one database; the tests assume an otherwise idle, empty database, and the others failed on leftover rows, duplicate session ids and claim counts); (b) **a single serialized, CI-shaped run (`pytest -m integration --allow-hosts=127.0.0.1`, fresh database, user `postgres`, one process) passed 1100 of 1100**; (c) the test passed 8 of 8 alone and 12 of 12 under four busy-loop processes on 2 CPUs (about 2.4 times slower), so CPU contention alone did not reproduce it; (d) this branch changes no calendar code or test (`git diff 0fbea4e HEAD` touches no calendar source, only a migration-head assertion and the e2e heading). Conclusion: not a regression from this branch; it is a shared-database contention failure in a test that assumes an exclusive database, and the CI integration job gives it one. The cause inside the test (a global `pg_stat_activity` match that is not scoped to this test's own backend, and a hard 5 s budget) is a plausible weakness but was **not** reproduced in isolation, so no change was made to unrelated behaviour and it is not claimed fixed. A hosted run remains the evidence that matters.

### 3. Component-level UI tests

`frontend/test-harness/audit.tsx` + `.html` mount the real `AuditSummarySection` with mocked API routes (same pattern as the attention-inbox and meeting harnesses), and `frontend/browser/audit-summary.spec.ts` uses a controlled browser clock and held responses: nothing loads or polls before or after the explicit load; clears when the tab becomes hidden and stays cleared on return; clears at the 60-second limit (still shown at 59 s) and never refreshes; a response arriving after the tab was hidden is discarded; a response arriving after the expiry cleared the request is discarded; a late response from a superseded request never replaces the newer summary; a 503 shows sanitized text with no counts and an explicit retry works with no automatic retry; an invalid payload (foreign actor) shows no counts and a 401 signs out exactly once; a window change clears the table and no `localStorage`, `sessionStorage` or cookie is written. Mutation checks: disabling both the abort and the generation/hidden guard failed the three late-response tests; removing the hidden-tab clearing failed three tests. All 27 local browser specs pass (`playwright.local.config.ts`, with `BUTLER_LOCAL_UI_TESTS=1 BUTLER_ENV=test`). The real-stack Playwright spec (`e2e/calendars.spec.ts`) remains edited but not run.

## Test evidence (local)

- `ruff check` and `ruff format --check`: clean. `bandit -r app ../pdf-worker -q`: no findings.
- Backend `pytest -m 'not integration' --allow-unix-socket`: 1578 passed.
- PostgreSQL 16 (local, disposable, CI-shaped: user `postgres`, fresh database, single process): full `pytest -m integration --allow-hosts=127.0.0.1`: **1100 passed, 0 failed** (20 minutes), including the audit-summary tests (6 in `test_audit_summary_postgres.py`) and `test_operations_postgres.py`. A migration round trip (downgrade to 0036, upgrade to head) ran in `test_revoked_grant_and_migration_round_trip`, in `test_migrations.py`, and repeatedly during the mutation checks.
- Frontend `npm test`: 793 passed (33 files); `npm run build` succeeded; `npm audit --audit-level=high`: 0 vulnerabilities; local browser specs: 27 passed.
- `check_repository.py` passed; `test_ci_scope.py` 23 passed; `build_feature_overview.py --check` passed (155 references, 99 named, 155 reviews); the generated overview and dashboard are unchanged.

## Not run or not verified

- Hosted CI, including the real-stack Playwright run that now exercises the audit summary in `e2e/calendars.spec.ts` (the existing operations test; its old "Audit review unavailable" assertion was replaced by the new heading, and it now loads the summary and checks the table, header and key set). That spec was edited but not run here: the container stack is unavailable locally.
- The component spec is a mocked-API harness; it is not real-stack evidence. The new browser harness specs are not wired into hosted CI by this branch (the existing local browser configuration is a local, opt-in check).
- No concurrency or lock-wait test of the new route beyond the shared `authority` path it reuses; no oversize case exists because the projection returns at most 21 rows.
- No real host, provider, private data or independent observer. Synthetic observations are not real-host evidence.

## Deviations and decisions

1. No new endpoint family or table: one function, one route, one section.
2. The summary counts only `auth.`, `admin.` and `operations.` events, a conservative choice so technical administration does not reveal content-domain activity volume. Widening is an owner decision.
3. Fixed windows (24 hours, 7 days) were chosen as a closed set; no target or threshold is asserted.
4. The runtime grant lives in `runtime_role.configure`, like the other reviewed functions; a database migrated but not role-configured cannot run the summary (it fails closed).

## Still required

Independent review, owner review and acceptance; hosted CI; real-stack coverage of the clearing behaviour; the rest of OPS-10 (overdue jobs, capacity trends, periodic/scheduled reports, delivery, alerting); OPS-09 observations; Gate 6 recovery suppression and Gate 11 clean-host recovery.
