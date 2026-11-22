# Spec 076 convergence record (22 November 2026)

**Merge record (documentation reconciliation, 22 November 2026):** this work was merged to `main` by the owner as PR #77 at merge commit `2a5a0cde92f3f4cfdaf12b53f442948989c267b2` (head `e631be90cbc65de4c586ac5a55614008b6dc60c0`). Merged is not verified; [PROJECT_MASTER.md](../../PROJECT_MASTER.md) owns status. The statements below describe the state when the evidence was recorded (history), including the `67bae82` commit being local and the branch unmerged.

Engineering evidence on the then-unmerged branch `work/mvp01-invoice/a3-implementation`, base `e088626331aff57d630d95faa721353a27bd468f`. First commit `67bae82d053c9f9e0b09747acabf447064600109` (local only, not pushed); a follow-up commit applies the review fixes below. The results in the table were obtained on the working tree that became `67bae82` unless the follow-up section says otherwise. Host: owner's Mac (Darwin, Python 3.13.5, Docker 29.9.3). Implementation, integration, testing, verification and acceptance are separate: **at recording time: not merged, not independently reviewed, not verified, not accepted** (merged since as PR #77; owner acceptance is recorded in PROJECT_MASTER.md for the bounded scope only). Nothing here is CI evidence.

## Results

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` (backend) | pass |
| Backend unit (`make check` backend step) | 2173 passed, **50 failed, 652 errors**, all in `test_recovery_set_*` / `test_recovery_staging.py` (modules not touched here). Cause: they need Linux `os.O_PATH`, absent on macOS (spec 075 already states macOS staging is unsupported). Because the backend step failed, `make check` stopped and its frontend/policy steps did not run as one command; they were run separately below. A clean pass of these modules needs Linux (CI). |
| `tests/test_synthetic_ledger.py` | 14 passed (incl. real-process SIGKILL before/after effect) |
| Frontend `npm test` / `npm run build` | 34 files, 846 tests passed / build ok (incl. `filing-api.test.ts`, 22) |
| `scripts/test_mvp01_owner.py` | 11 passed at `67bae82`; 13 passed after the first follow-up (fake docker: subnet/port/config/volume/reset refusals and the missing-config recovery) |
| `check_repository.py`, `test_ci_scope.py`, `build_feature_overview.py --check` | pass; re-run immediately before `67bae82` (repository policy, feature overview 155 references) and again for the follow-up commit |
| Disposable PostgreSQL 17 (own container, `butler_test`, `BUTLER_ENV=test`, `BUTLER_RUN_DB_TESTS=1`), full `-m integration` incl. existing `mvp03_journey`, `filing_restart`, `notification_restart` and 10 new `mvp01_journey` tests | **1207 passed** on a freshly recreated database. An earlier run on a reused database showed 2 failures in `test_document_answers_postgres`/`test_documents_postgres` caused by a document left active by my first, failed test teardown (a scope-revocation test); no guard was bypassed — the database was recreated and the test now restores the scope. This full run predates all follow-up commits; per A1, A5 re-ran the full suite at `1762859` with the same 1207 count (not re-run by me). |
| Live rehearsal, API driver `scripts/mvp01-owner-check.py journey` then `verify` after `restart` and after `restart --kill` | 30 checks passed on `journey` at `67bae82` (35 after the first follow-up added AC1 and the explicit peer-scope denial) (AC2–AC7, AC10, AC11); `verify` passed after both restarts (same document/title/revision, review, plan, one terminal filing, history, reminder not redelivered, agenda unchanged); ledger `effects: 1, calls: 1` before and after both |
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

## Independent findings and follow-up (commit after `67bae82`)

A4 (independent review of `67bae82`) reported no high-severity defect; A5 (verification) reported the backend journey, restarts (including SIGKILL) and failure scenarios passing on a scratch-patched stack, with the browser UI **not** run by A5. Neither is acceptance. Reports were relayed by A1; their files were not readable from this session, so the fixes follow A1's summary of the findings.

Changed in the follow-up:
- `reset` now works when the generated config is missing but project volumes exist (the recovery the `start` refusal message tells the owner to use). It is still limited to the exact project by Compose label and name prefix and needs the typed project name. Tested through the real recovery path (refused `start` with orphaned volumes, wrong confirmation, confirmed reset, foreign-prefixed volume, empty environment).
- Subnet refusal now names the conflicting Compose project and says to stop it without `-v`; guide step 0 says the same.
- `scripts/mvp01-owner-check.py`: dead `if False` code removed; AC1 checks the real `/auth/me` identity and exact scopes; AC2/AC10 require an explicit 403 for the peer scope and a readable own private scope instead of passing on empty denials; the peer-login claim was removed and the output states that signed-in peer isolation is evidenced only by the PostgreSQL tests (the peer password is random and never retained).
- Ledger: undecodable entries raise the fixed `LedgerError` instead of a raw decode error; a test pins both `put` and `lookup`.
- Revoked-scope PostgreSQL test renamed to what it proves (scope revocation only; session revocation not covered by this test).
- Browser spec: removed the swallowed `.catch`. Panel: polling no longer starts while a request is in flight; request and cancel controls are shown only to the document owner (a short note explains it to others); first-page-only listing and history are stated in the panel and the spec.

Re-run for the first follow-up (`1762859`, this Mac, 22 November 2026): ruff check/format; ledger unit tests (14); `scripts/test_mvp01_owner.py` (13); frontend typecheck, full suite (846) and build; repository policy and feature-overview checks; disposable PostgreSQL 17 (fresh database, `BUTLER_ENV=test`) `test_mvp01_journey_postgres`, `test_filing_restart_postgres`, `test_notification_restart_postgres`, `test_mvp03_journey_postgres`, `test_filing_fence_postgres` = **70 passed**; live driver on the patched verify stack = **35 checks passed**, then SIGKILL restart and `verify` passed; `reset` with the generated config deleted was refused by `start` and recovered by a confirmed `reset`; browser spec `journey` and, after a container restart, `resume` passed on a fresh database. The verify project, temporary compose copy and test PostgreSQL container were removed.

## Real limits to keep in view

Live evidence came from a patched copy of the script/compose on a different subnet, ports and project (the fixed subnet was held by another stack); the real `start` has not been run by an agent. A5 did not run the browser UI; this session's earlier browser run used a Linux Playwright container and predates the follow-up. The sign-in limiter allows 5 attempts per account per 15 minutes and was never cleared, which constrains repeated runs. A host reboot and a clean-host recovery are not exercised. Whether CI should run `scripts/test_mvp01_owner.py` and the exact wording of the 22 November decision on commit authorization are owner/A6 decisions and were not changed.

## Second follow-up (owner trial and A4/A5 residuals)

Recorded as fixes or documented limits, from A1's relay of the owner's trial and the re-review/re-verification findings (report files were not readable from this session):
- A non-owner editor no longer sees "Synthetic filing data is invalid": the strict client now validates the listing against the signed-in caller and the panel shows the owner-only note (server remains the authority; client test added).
- "Suggest filing plan" is disabled with a visible reason until issuer, invoice number and issue date are confirmed and saved (manual destination remains available).
- After signing in again the filing panel appears only after *Load invoice review*: documented in the guide (not changed in code).
- Reminders are enabled by default (Europe/Paris, quiet hours 22:00–08:00, limit 5); the guide is corrected, the preferences form explains "nothing to save" locally instead of surfacing the server's `reminders.no_change` conflict, and the guide says where the *Remind me in Butler* control is. The live driver's wording ("opt-in") in earlier sections reflects what I believed then.
- Start-refusal and guide now warn that `reset` also removes a rehearsal started from another checkout, and which reset guards apply without the generated config; ledger crash-window limits and the AC10 "session revocation not exercised" wording are in the spec. Not done: an optional panel component test (no component-test harness; the strict client is unit-tested).

## Results for the later commits (`a09dc91`, `a1e0331`, and the documentation fixes after them)

Ran on this Mac: ruff check/format (pass); ledger unit tests (14 pass); frontend full suite (847 pass), typecheck and build (pass; there is no separate lint step beyond `tsc`); `check_repository.py` (pass); `test_ci_scope.py` (23 tests pass, before and after the workflow edit); `build_feature_overview.py --check` (155 references, pass); workflow YAML parses; `scripts/test_mvp01_owner.py` = OK with **4 skipped** (the owner's running rehearsal held loopback ports 18081/18444, and the port-dependent cases skip by design rather than disturb it; they last ran and passed with the ports free, before the test was changed to use an isolated throwaway git repository instead of reading this repository's `.git`, so those four are unverified against that change until CI); browser spec `journey` and, after a container restart, `resume` passed on a separate verify project after the panel changes (Linux Playwright container, public CA only), which was then torn down with the owner's stack untouched.

**Not run** for these commits: the PostgreSQL suites (no backend code changed), the live API driver, the real `start`, a Linux run of `scripts/test_mvp01_owner.py` and of the `recovery_*` modules (first exercised by CI), a host reboot and clean-host recovery. On 22 November 2026 the owner accepted the journey as tried on `17628594e037397ad013333b5e6dc785757aa8c7` and re-confirmed it for `193ccb865eaa63cb85b408b734778ad2629fa920` after trying the three changed screens (see PROJECT_MASTER.md and DECISIONS.md); commits after `193ccb8` change documentation or printed text only and are not separately accepted.

## Owner-observed evidence (22 November 2026)

Links the steps the owner personally ran to the scope they answer. Labels: *owner-run, result not reported individually*; *owner-reported*; *A1-database/ledger-confirmed* (read-only, 22 Nov 2026); *agent-only*. This promotes no gate.

| # | Owner step | Spec 076 | Underlying spec / gate | Evidence level |
|---|---|---|---|---|
| 1 | Start stack, HTTPS sign-in (CA trusted by the owner) | AC1, R6, R7 | Gate 1/2 (CORE-02/08/09, UI-01) | owner-run; healthy start and CA fingerprint seen by A1; mobile viewport **not** reported |
| 2 | Daily overview 2026-11-24 | AC2, R8 | Gate 4 (ORG-01/02, MVP-02; spec 062) | owner-run, result not reported individually |
| 3 | Import the same `.eml` twice, review the source | AC3, AC4 | Gate 7 (DOC-01/02/03, MVP-03; specs 056, 058) | owner-run, result not reported individually; document `22d01f58-c5f7-437d-984f-eaae15be01bd` seen in API logs |
| 4 | Cited question "What is the total amount?" | AC4, AC11 | Gate 3 (CORE-06/10; spec 053) | owner-reported ("seems good"); the model is **simulated** |
| 5 | Reminder scheduled, delivered, acknowledged | AC5 | Gate 5 (ORG-03, CORE-11/13, REM-01; spec 047) | A1-database-confirmed: scheduled 20:37:14, delivered 20:38:08, acknowledged 20:40:42 (Europe/Zurich), each once; task stayed open |
| 6 | Invoice review, filing plan, approve plan only | AC6, R1 | Gate 7 (specs 056, 057) | owner-run; API logs show review/plan/approve_plan 200 (after earlier 422s on plan suggestion with unconfirmed fields) |
| 7 | Request synthetic filing | AC7, R1–R3 | Gate 7 (MVP-03; spec 069) | A1-ledger-confirmed: calls 1, effects 1, entries 1; recorded sha256 `cf33de5445929268ba31d57594c2cbfa05e978ffe18268b1c6b4ec991f2b8223` and size 140 equal the fixture attachment's |
| 8 | `restart`, `restart --kill` (twice), stop + start, second container restart | AC8, R5, R6 | Gate 5/10 (OPS-09/10) | A1-ledger-confirmed after each: same entry, effects 1, no re-delivered reminder |
| 9 | Rebuild to `193ccb865eaa63cb85b408b734778ad2629fa920`; plan-suggestion screen, reminder-preferences screen, filing panel after sign-in | AC6, AC7, R1 | Gate 7 | owner-reported ("All three screens work"); ledger unchanged after the rebuild (A1-confirmed) |
| 10 | stop; reset guard; subnet refusal | AC12, R6, R7 | INSTALL-01/02 | owner ran `stop` (data kept); reset guard and subnet refusal are **agent-only** |

AC9 (failure scenarios) and AC10 (peer, stale, malicious-path refusals) were **not** exercised by the owner's own run: agent-only (A5 live run, author's PostgreSQL tests). This mapping promotes no gate; Gates 3, 4, 5 and 7 stay partial and not accepted; Gate 7 real-destination evidence remains missing; the composite MVP-01 acceptance is for the stated synthetic scope only.
