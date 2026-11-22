# Spec 076 convergence record (22 November 2026)

Engineering evidence on the **unmerged** branch `work/mvp01-invoice/a3-implementation`, base `e088626331aff57d630d95faa721353a27bd468f`, working tree uncommitted. Host: owner's Mac (Darwin, Python 3.13.5, Docker 29.9.3). Implementation, integration, testing, verification and acceptance are separate: **not merged, not independently reviewed, not verified, not accepted.** Nothing here is CI evidence.

## Results

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` (backend) | pass |
| Backend unit (`make check` backend step) | 2173 passed, **50 failed, 652 errors**, all in `test_recovery_set_*` / `test_recovery_staging.py` (modules not touched here). Cause: they need Linux `os.O_PATH`, absent on macOS (spec 075 already states macOS staging is unsupported). Because the backend step failed, `make check` stopped and its frontend/policy steps did not run as one command; they were run separately below. A clean pass of these modules needs Linux (CI). |
| `tests/test_synthetic_ledger.py` | 14 passed (incl. real-process SIGKILL before/after effect) |
| Frontend `npm test` / `npm run build` | 34 files, 846 tests passed / build ok (incl. `filing-api.test.ts`, 22) |
| `scripts/test_mvp01_owner.py` | 11 passed (fake docker: subnet/port/config/volume/reset refusals) |
| `check_repository.py`, `test_ci_scope.py`, `build_feature_overview.py --check` | run after the master edit; re-run after this file exists (see final report) |
| Disposable PostgreSQL 17 (own container, `butler_test`, `BUTLER_ENV=test`, `BUTLER_RUN_DB_TESTS=1`), full `-m integration` incl. existing `mvp03_journey`, `filing_restart`, `notification_restart` and 10 new `mvp01_journey` tests | **1207 passed** on a freshly recreated database. An earlier run on a reused database showed 2 failures in `test_document_answers_postgres`/`test_documents_postgres` caused by a document left active by my first, failed test teardown (a scope-revocation test); no guard was bypassed — the database was recreated and the test now restores the scope. |
| Live rehearsal, API driver `scripts/mvp01-owner-check.py journey` then `verify` after `restart` and after `restart --kill` | 30 checks passed on `journey` (AC2–AC7, AC10, AC11); `verify` passed after both restarts (same document/title/revision, review, plan, one terminal filing, history, reminder not redelivered, agenda unchanged); ledger `effects: 1, calls: 1` before and after both |
| Live rehearsal, browser (`mvp01-owner.spec.ts`, Chromium 1.65 in a Linux container; public CA in its NSS store, `ignoreHTTPSErrors` false, no flags) | `journey` passed (same email twice, replay, review, plan-only approval offers no filing, separate request, Filed, history, mobile-width no overflow); `resume` after container restart (first attempt failed on a faulty selector in my spec, corrected) and after process kill passed |
| Rehearsal `reset` | wrong confirmation refused; confirmed reset removed only the verification project's containers/networks/volumes; other environments (8 containers) untouched |

## Evidence labels and deviations

- **Real `start` was not run as specified.** The owner's `butler-poc` stack holds `172.29.243.0/28`; the script refused, naming `butler-poc_app`, and stopped nothing (this is also unit-tested). Live evidence therefore came from a **deviation copy**: identical script/overrides with project `local-assistant-core-mvp01-verify`, ports 18091/18454 and subnet `172.29.245.0/28` (compose copy with the subnet and Caddy/API proxy address replaced). Differences: those constants only. Reproduce on the real stack by stopping the conflicting environment, then `bash scripts/mvp01-owner.sh start`.
- **Labels.** "Container restart" = `docker compose restart`; "process kill" = SIGKILL of api/workers; real-process SIGKILL of the worker is in the PostgreSQL tests. Host reboot and clean-host recovery were **not** exercised. Docker Desktop paused while the Mac slept once, delaying one reminder pass; the reminder was still delivered exactly once.
- Reminder preferences are an owner opt-in (default policy Paris/quiet hours); the guide and driver enable them explicitly (discovered during the run).
- The simulated model cites the first line of its retrieved window; the fixture question targets the total line.
- The browser run used a throwaway Linux container (image `mcr.microsoft.com/playwright:v1.65.0-noble`, a dependency download) and a loopback forwarder to Caddy; that helper is not delivered. The browser spec does not cover the daily overview or reminder UI (covered through the API driver and existing specs) and was not run in CI.
- No Mac Keychain trust change was made.

## AC status (agent evidence only)

AC1 partial (stack/TLS/sign-in exercised on the deviation stack; real-subnet start blocked). AC2–AC8, AC10, AC11 exercised by driver and/or browser and/or PostgreSQL tests. AC9 PostgreSQL (kill points, timeouts, inconclusive lookup) and unit; the owner-visible `scenario` command is implemented but its three controls were not exercised live. AC12 stop/restart/reset exercised (stop only through unit test); reset exercised live on the deviation project.

## Open

Independent review (A4), A1+A5 verification, owner's personal run on the real stack, CI evidence, and Linux confirmation of the `recovery_*` modules remain. Register status labels were deliberately not changed (the register fingerprint is tied to the hand-curated snapshot; the label changes only after merge).
