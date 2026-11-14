# Spec 073 tasks

Implementation authorized by the owner on 14 November 2026. Contract: [spec.md](spec.md). *(Historical wording, written on the open branch: "Branch engineering only: nothing here is merged, verified or accepted.")* **Current status (14 November 2026):** implemented in PR #37, merged as `4a7e624` (see the merge record in [convergence.md](convergence.md)); the merge is integration only. Nothing here is independently verified or accepted, and no requirement, gate, priority or acceptance status changes.

## Implementation

- [x] Shared eligibility rules E1–E8 (`backend/app/queue_eligibility.py`), each a verbatim restatement of the worker's existing condition with `now` replaced by `t`; no grace parameter and no observer guard.
- [x] Workers use the shared rules at their own single `now`: `jobs.claim`, `reminder_worker.candidates`, `notification_worker.enqueue_pass` and `candidates`, `filing_worker.candidates`. Joins, ordering, limits and locks unchanged.
- [x] Observer `operations.work_queries` / `observe_work` at `now − 120 s` with the observer-only eligible-since guards (reminders: row and preferences `updated_at`; notifications: `delivered_at` for enqueue, delivery `updated_at`, preferences `updated_at` for paused rows; filing: `updated_at`). Stalled only for an expired lease (jobs) or in-flight deadline (notifications, filing); reminders never stalled.
- [x] `POST /api/v1/operations/work-status`: strict `{scope:"technical_admin"}`, existing technical-admin authority path, 2 s lock / 5 s statement timeouts (bound `set_config`, transaction-local), session revalidation and 60-second receipt check, one metadata-free `operations.work_status` audit committed before release, all-or-nothing response.
- [x] Migration `0038_work_status_audit_category`: `CREATE OR REPLACE` of `butler_audit_summary` with one added literal (`operations.work_status` → `operations_read`); downgrade restores 0037's exact body. Migration-head assertions moved to 0038.
- [x] Frontend: `parseWorkStatus` / `readWorkStatus`, `WorkStatusSection` (explicit load, exact §1.8 copy, 60-second expiry, hidden-tab, session/grant change and late-response clearing, no persistence) inside the Operations overview.

## Acceptance tests (spec §5)

- [x] 1–4, 4a, 4b, 5–11, 16: `backend/tests/integration/test_work_status_postgres.py` (restricted runtime role; fresh isolated database per test via `backend/tests/work_status_support.py`).
- [x] 12–15: `backend/tests/integration/test_queue_eligibility_postgres.py` (frozen pre-refactor statements, ordered candidate IDs, no-delay, rule equality) and `backend/tests/test_queue_eligibility.py` (compiled-condition equality).
- [x] 17: existing worker and restart suites run unmodified.
- [x] 18–19: `backend/tests/integration/test_audit_summary_postgres.py` (taxonomy case; `0038 ↔ 0037` round trip with function guards).
- [x] 20: `backend/tests/test_operations_work_status.py` (SQLite).
- [x] 21: `frontend/src/operations-api.test.ts` (parser, mocked).
- [x] 22: `frontend/browser/work-status.spec.ts` with `frontend/test-harness/work-status.*` (mocked component tests; local opt-in, not hosted CI evidence).
- [x] 23: `frontend/e2e/calendars.spec.ts` operations group (real stack; runs only in hosted CI).
- [x] 24: hosted CI on the PR head `2408a68` passed all six jobs (run 43615751104). The merge commit `4a7e624` also passed (run 43624054196). CI results only: neither is verification or acceptance.

## Not authorized here

- [ ] Owner review, merge and acceptance; any OPS-09/OPS-10 or Gate 10 status change. (Merged as PR #37 at `4a7e624`, 14 November 2026. Independent verification, owner acceptance and any status change are not done and stay unchecked.)
