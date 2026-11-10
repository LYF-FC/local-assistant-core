# Verification

Run `make check`: locked dependency sync, backend Ruff/format/unit tests, frontend client tests/build, repository invariants and CI scope/gate contracts. The fixture target must be development/test; production/staging startup is refused.

For actual PostgreSQL evidence, explicitly opt in with `BUTLER_RUN_DB_TESTS=1`, `BUTLER_ENV=test` and a disposable `BUTLER_POSTGRES_DB` beginning with `butler_test`. Use the intended local PostgreSQL host/port and synthetic credentials, then run `uv run --locked pytest -m integration --allow-hosts=127.0.0.1 --durations=30` from backend. Do not weaken socket/target guards or reuse an owner database. Explicit migration round trips and runtime-role/idempotence tests remain included. A fresh test target includes both `public` and the separate `work` schema. If resetting a positively identified disposable target between focused and full runs, recreate the entire disposable database; dropping only `public` leaves Work objects that make upgrade-from-empty fail. Never use a database reset against an owner installation.

`scripts/test-db-restore.sh` requires the exact disposable `butler_test` database and an unambiguous `BUTLER_CI_POSTGRES_CONTAINER`; it exercises actual dump/isolated restore, original/history/tombstone preservation, session/access quarantine and existing recovery procedures. It is destructive test infrastructure.

`scripts/test-containers.sh` validates fresh synthetic non-root containers, HTTPS/Origin/proxy boundaries, general browser scenarios and an independent optional Work phase plus recovery drills. `test-ci-browser.sh` imports a synthetic public CA only in a disposable Linux runner. It must never modify an owner trust store or bypass certificate validation. No private records or real services are needed.

The new public repository must obtain its own exact-head selected/full CI evidence. Prior private runs and local verification do not become new hosted passes.

## Database users: container tests and PostgreSQL tests differ

`postgres` names the database engine and often its image; it is not the migration username for every test environment. Read the selected harness before writing or running a fixture.

| Harness | Privileged migration/fixture connection | Restricted application connection | Disposable database |
|---|---|---|---|
| Compose/container/HTTPS CI (`scripts/test-containers.sh`) | **`butler` by default**, from `BUTLER_POSTGRES_USER` in Compose | `butler_runtime` for API and DB-backed workers | `butler_test_container` |
| PostgreSQL integration and logical restore CI | **`postgres`**, explicitly configured by that job/harness | `butler_runtime` where runtime-role tests apply | `butler_test`; isolated restore `butler_test_restore` |

The [Compose definition](../infra/core/compose.yml) and [CI workflow](../.github/workflows/ci.yml) are authoritative. `migrate` and `role_setup` use the configured migration owner. API and DB-backed worker services use the separate restricted role and runtime secret. Local overrides may choose a different migration-owner name; they do not change the configured CI default or grant runtime privileges.

### Portable fixture rule

A synthetic fixture that can run in Compose **must not require the username `postgres`**. Keep explicit test-environment and disposable-database guards, then verify the authority actually needed. For a privileged seed, require ownership of the relevant table before reading fixture records or writing intent, for example:

```sql
SELECT pg_get_userbyid(relowner) = current_user
FROM pg_class
WHERE oid = 'public.manual_tasks'::regclass;
```

Choose the actual table being seeded and refuse a false result before any mutation. `BUTLER_POSTGRES_USER` or a username allowlist alone is not proof of table ownership. Keep `butler_runtime` unable to run privileged fixtures; do not broaden its grants, remove the environment/database guards, or clear authentication counters to make a test pass. Emit only a fixed non-secret refusal message.

Fixtures intentionally exclusive to the fixed PostgreSQL/restore harness may retain its explicit `postgres` guard. Do not bulk-replace those guards or run destructive restore scripts through the container/browser harness. Portability is a declared fixture contract, not a reason to weaken isolation.

### Fixture preflight before pushing

1. Match the fixture's environment, database, migration owner and service to the table above. Use synthetic data and a separate disposable project.
2. Run privileged seed/check operations through `migrate`. Test rejection through the restricted API/runtime connection **before** privileged seeding, so an existing-row conflict cannot masquerade as an authorization denial.
3. Verify the affected container/worker/browser phase using CI's default **`butler`** migration owner. A local pass obtained only by overriding it to `postgres` does not verify the CI setup. Test additional owner names when the fixture promises that portability.
4. Keep runtime, permissions, authentication limits and required coverage unchanged. Record the exact command/harness and result in the PR; a failed final gate may simply reflect an earlier failed job rather than a second independent defect.

After publishing, report the expected CI jobs and stop. Verify completed results when the owner reports readiness or requests a check; do not poll while waiting. A documentation-only check validates policy/text, not runtime behavior.

## Feature overview and review checks

`make policy` verifies reproducible generated overview/dashboard output and all-reference review coverage, plus CI scope/gate tests. Run `python3 scripts/build_feature_overview.py --check` for a direct offline/no-write check. Generator/template/policy changes need negative cases for missing/duplicate references, unsupported acceptance claims, stale snapshot/cohort/stage metadata, tampered output and embedded-script source text. Validate the standalone HTML filters, mobile layout and absence of network requests; it is not served by the application and does not alter app/DB/browser acceptance claims.


Spec060 adds installation unit/client tests, actual runtime PostgreSQL concurrency/authority/guard tests, two independent synthetic configuration datasets, a full restore fixture preserving installation identity/history and trusted HTTPS mobile/import/export/conflict/late-response checks. `installation.spec.ts` runs in the fresh answers/calendar/routines/invoice/email phase with `BUTLER_INSTALLATION_BROWSER_TESTS=1`. Browser provisioning now checks users-table ownership before mutation and proves runtime refusal before the privileged seed. The native restore fixture deliberately retains the fixed postgres owner guard.


Spec062 daily-overview UI cases share the existing calendar synthetic HTTPS phase (`calendars.spec.ts`, BUTLER_CALENDAR_BROWSER_TESTS=1), using existing accounts and protected APIs. No fixture/worker privilege or additional CI phase is added. Client negative cases cover bounded protected reads, source/actor/owner/scope mismatch, denials, unavailable sections, abort and lifetime limits. Browser cases prove other-owner privacy, current-source navigation/context, first-page limits, failure/late/hidden/expiry behavior and actual session revocation. Keep default Compose ownerbutler/runtime isolation and real authentication limits unchanged.
