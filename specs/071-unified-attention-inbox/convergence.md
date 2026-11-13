# Convergence — unified attention inbox (first slice)

**Implemented on branch `codex/impl-071-attention-inbox`; locally tested; not independently verified, not merged, not accepted.** The Evidence column below records only results actually produced on this branch in a disposable local environment (synthetic data). Hosted CI and the compose container e2e have not run on this change. Gate 2 stays open (criterion unchanged: "Dashboard exposes agenda, pending approvals, reminders, failures and authorized search."); CORE-08 and UI-01 stay partial; no status counts changed; the five-priority order stays unapproved. Implementation, testing, verification and acceptance are separate facts, and only the first two are claimed, locally.
## What convergence must show

| Spec requirement | Source | Required evidence | Evidence |
|---|---|---|---|
| Inbox view composing the six sections for one granted scope; search entry reuses spec 067 | spec §Delivers; CORE-08, UI-01 | Client and browser workflow results (A1) | Vitest `attention-inbox.test.ts` (48 tests) and `browser/attention-inbox.spec.ts` (12 Playwright tests, synthetic component harness, not the real stack) passed locally. |
| Approvals list: pending, unexpired, bound only; allow-listed fields; no payload, hash, policy, approver or requester id; paging | spec §Pending approvals; CORE-04 | Backend allow-list, status, expiry, legacy and cursor tests (A2, A4, E1, E2) | `test_approval_query.py` (12 tests) passed locally; strict client parsers tested in Vitest. |
| "Requested by you" label; no self-approval restriction implied | owner decision 3 | Label tests (A3) | Backend and client tests passed locally; the label implies no self-approval restriction. |
| One metadata-only audit event per list request; failure withholds results; event name rechecked and pinned | owner decision 2; CORE-05 | Event shape/count tests, real-role PostgreSQL insert and induced failure (U1, U2) | `integration/test_approval_query_postgres.py` (5 tests) with `test_approval_postgres.py` (22 passed together) on local PostgreSQL 16 under the restricted runtime role, including an induced audit-insert failure that withholds the page and leaves no event. Event name rechecked and pinned. |
| Approvals evidence-only: no destination, no Open, decide, cancel or consume control, no request to approval operation routes | owner review; CORE-04 | Browser and network-recording assertions (N3, S1) | Browser spec asserts no Open control for approvals and that only the six read routes are requested; passed locally (harness). |
| Tasks (open overdue) and reminders (delivered) with owner-only and shared-read-only rules; routine-generated tasks also under ORG-03 | REM-01, ORG-03 | Visibility tests (P2, P3); routine-origin check | Visibility tests passed locally. Routine origin is not shown: the existing task response does not provide it and no field was added. |
| Documents needing review | CORE-10 | Unreviewed and extraction-failed selection tests | Client selection tests passed locally. |
| Filing and notification failures with uncertainty wording and owner-only visibility | DOC-03, CORE-11 | Failure-state and visibility tests (F1, P2) | Client and backend tests passed locally. |
| Explicit refresh, 60-second and approval-expiry clearing, non-atomic notice, late-response discard | spec §Refresh | Expiry and clearing tests (E3, E4) | Vitest and browser expiry, hidden-tab, scope-change and soonest-approval-expiry tests passed locally. |
| Source failure never appears as empty; per-source retry; empty-state sentence only when every source loaded | spec §Refresh | Partial-failure tests (F1–F4, U2) | Vitest tests passed locally. |
| Authorization denial clears every section; navigation rereads under current authorization; revoked grant handled | spec §Navigation | Denial and revocation tests (N1, N2) | Vitest and browser denial tests (401/403/404/410) passed locally. |
| Duplicate references render once; separate record kinds not merged | spec §Item model | Dedup tests (D1) | Vitest tests passed locally. |
| No state-changing request from the inbox | spec | Network-recording test (S1, S2) | Browser network test passed locally (harness). |
| Mobile 390×844, keyboard and live-region behaviour (existing obligations only; REV-03 not claimed) | spec §Mobile | Browser workflow (mobile) | 390×844 run showed no horizontal overflow; passed locally. No screen-reader or device testing. |

## Deviations and decisions

1. Audit event name `approval.query`: rechecked; `audit_events.event_type` is an unrestricted varchar(128) with no code allow-list, so the name is used and pinned by a test. No migration.
2. Routine origin: not shown (see above); no field added.
3. Filing and notification cards link at scope level (Documents or Reminders view), not to a specific record, because those records lack the fields the existing source-navigation target needs.
4. Approvals have no authorized in-app destination; adding one is a later owner decision.
5. Open overdue tasks only; widening is a reviewer decision.

## Local checks that ran (synthetic data, disposable environment)

- Backend: `ruff check` and `ruff format --check` passed; `pytest -m 'not integration' --allow-unix-socket`: 1564 passed, 1094 deselected.
- Frontend: `npm test` 752 passed (32 files); `npm run build` succeeded (existing chunk-size warning only).
- Policy: `check_repository.py` passed; `test_ci_scope.py` 23 passed.
- PostgreSQL 16 (local, disposable `butler_test_i71`): approval query, approval, identity, manual-task and migration suites: 58 passed. The full integration suite was started but stopped after about 6% because it was too slow locally, so it was **not** completed here; hosted CI runs it.
- Browser: `browser/attention-inbox.spec.ts` 12 passed with `playwright.local.config.ts` (local synthetic mode). This config is not run by CI.
- Generators: `build_feature_overview.py` and `--check` ran; overview and dashboard output did not change.
- Mutation spot-checks of the new backend and client code were run locally; surviving mutants led to stronger tests.

## Not run or not verified

- Hosted CI on this change has not run. The `containers` job (compose e2e, `scripts/test-containers.sh`) could not run locally (no container runtime), and no real-stack Playwright spec for the inbox was authored, so the inbox browser tests are not exercised by CI. This is a gap for the reviewer.
- `bandit`, `pip-audit` and `npm audit` were not run locally.
- Local-only workarounds: `--allow-unix-socket` for pytest, and Chromium build symlinks for Playwright. Neither changes repository files.
- Private-host and mobile-device acceptance, screen-reader testing, real providers and owner acceptance of Gate 2 are not done and are separate.

## Still required after review

The merged commit and PR number once merged (recorded only after merge); hosted CI results; owner decision on the gaps above. Branch engineering is not merged delivery.
