# 072 convergence

**Implemented on the local branch `codex/spec-072-operations-audit-summary` (from `main` at `0fbea4e`); locally tested; not pushed, not independently verified, not merged, not accepted.** Evidence below was produced in a disposable local environment with synthetic data. Gate 10, OPS-09, OPS-10 and every other status, count and gate are unchanged; the first slice of OPS-10 exists, the rest is open. Implementation, testing, verification and acceptance are separate facts; only the first two are claimed, locally.

## Requirement mapping

| Contract item | Source | Evidence |
|---|---|---|
| Count-only projection; runtime role keeps no audit SELECT | spec §Scope, §Authorization; OPS-10 | `integration/test_audit_summary_postgres.py::test_function_guards_and_privileges` (runtime role cannot SELECT or count `audit_events`; append-only trigger still refuses delete) |
| Closed category/outcome catalogue, exact window, content-domain and lookalike exclusion | spec §Categories | `test_mapping_window_and_exclusions_are_exact` (20 mapped cases, 5 excluded types, outside-window and future rows; mutation check: adding `documents.` to the function makes it fail) |
| Function guards: definer, fixed `search_path`, no PUBLIC execute, actor must hold current grant, window only 24/168 | spec §Authorization | `test_function_guards_and_privileges` |
| Strict request, current authority, CSRF/Origin, revoked grant | spec §Authorization | `tests/test_operations_audit_summary.py` (SQLite) and `test_api_shape_denials_and_metadata_only_audit`, `test_revoked_grant_and_migration_round_trip` (PostgreSQL) |
| Exact response shape, totals equal column sums, no ids/actors/metadata | spec §Response | `test_api_shape_denials_and_metadata_only_audit`; client `parseAuditSummary` tests (16 rejection cases) |
| Audit of the read is metadata-only; failure withholds the response | spec §Audit | `test_audit_failure_withholds_the_summary` (induced insert failure on the runtime engine; no payload, no row) |
| No fabricated counts outside PostgreSQL | spec §Failure | `test_non_postgres_never_fabricates_counts_and_does_not_audit_success` |
| Migration round trip | spec §Migration | `test_revoked_grant_and_migration_round_trip` (downgrade to 0036 drops the function, upgrade restores it); migration-head assertions moved to 0037 in `test_calendar_schema.py` and `scripts/test-db-restore.sh` |
| Client parsing, explicit load, clearing, no persistence | spec §UI | `operations-api.test.ts` (58 passed); the section's clearing and rendering are exercised only by the real-stack spec below (no mocked component harness was added) |

## Test evidence (local)

- `ruff check` and `ruff format --check` (backend and pdf-worker): clean.
- Backend non-integration `pytest -m 'not integration' --allow-unix-socket`: 1578 passed.
- PostgreSQL 16 (local, disposable, runtime role): `test_audit_summary_postgres.py` 5 passed and `test_operations_postgres.py` 4 passed. Full integration suite (`pytest -m integration`, local PostgreSQL 16): 1097 passed, 2 failed, none in the new or operations tests. `test_installation_postgres.py::test_two_actual_configuration_databases_...` fails only because it asserts the database user is `postgres` and this local environment uses a different superuser name (the same failure occurred before this branch; hosted CI runs it with the expected user). `test_calendars_postgres.py::test_session_expiry_after_actual_row_wait[briefing]` failed once while a second suite ran concurrently and passed (5 of 5) when rerun alone; it is a timing sensitivity, not investigated further and not claimed as fixed.
- Frontend `npm test`: 793 passed (33 files); `npm run build` succeeded (existing chunk-size warning only); `npm audit --audit-level=high`: 0 vulnerabilities.
- `check_repository.py` passed; `test_ci_scope.py` 23 passed; `build_feature_overview.py --check` passed (155 references, 99 named, 155 reviews); the generated overview and dashboard are unchanged.
- `bandit -r app ../pdf-worker -q`: no findings.

## Not run or not verified

- Hosted CI, including the real-stack Playwright run that now exercises the audit summary in `e2e/calendars.spec.ts` (the existing operations test; its old "Audit review unavailable" assertion was replaced by the new heading, and it now loads the summary and checks the table, header and key set). That spec was edited but not run here: the container stack is unavailable locally.
- No mocked component test of `AuditSummarySection` clearing (hidden tab, expiry, late response) exists; the overview's equivalent real-stack test was not extended.
- No concurrency or lock-wait test of the new route beyond the shared `authority` path it reuses; no oversize case exists because the projection returns at most 21 rows.
- No real host, provider, private data or independent observer. Synthetic observations are not real-host evidence.

## Deviations and decisions

1. No new endpoint family or table: one function, one route, one section.
2. The summary counts only `auth.`, `admin.` and `operations.` events, a conservative choice so technical administration does not reveal content-domain activity volume. Widening is an owner decision.
3. Fixed windows (24 hours, 7 days) were chosen as a closed set; no target or threshold is asserted.
4. The runtime grant lives in `runtime_role.configure`, like the other reviewed functions; a database migrated but not role-configured cannot run the summary (it fails closed).

## Still required

Independent review, owner review and acceptance; hosted CI; real-stack and mocked-UI coverage of the clearing behaviour; the rest of OPS-10 (overdue jobs, capacity trends, periodic/scheduled reports, delivery, alerting); OPS-09 observations; Gate 6 recovery suppression and Gate 11 clean-host recovery.
