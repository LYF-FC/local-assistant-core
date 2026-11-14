# 072 tasks

Status of each item is a local-branch fact only. *(Historical statement written on the open branch: "Nothing is verified, merged or accepted.")*

> **Current status (14 November 2026):** implemented in PR #35, merged as `41aa5f3`, 14 November 2026 (see the merge record in [convergence.md](convergence.md), which also records that the push to `main` at the merge commit failed in `postgres` and a later push passed). The merge is integration only; nothing here is independently verified or accepted.

- [x] Contract: spec.md (this directory).
- [x] Migration 0037 adds `butler_audit_summary(text, timestamptz, integer)` (actor derived in-database from the live session token); downgrade drops it.
- [x] `runtime_role.configure` grants EXECUTE on the function and still grants no audit SELECT.
- [x] Backend `operations.audit_summary` and `POST /api/v1/operations/audit-summary`.
- [x] Frontend strict parser, explicit-load section in the Operations overview.
- [x] Tests: unit (auth, shape, validation, audit-failure), PostgreSQL integration under the restricted runtime role (counts, exclusions, denial, function guards, migration round-trip), Vitest, mocked browser spec.
- [x] Documentation: OPERATIONS_OVERVIEW.md, FEATURE_REGISTER OPS-10 note, PROJECT_MASTER, convergence.md.
- [x] Pre-push review remediation (local): actor substitution closed (UUID parameter replaced by session-token binding; restricted-role PostgreSQL substitution test); component-level browser tests for the audit section (`browser/audit-summary.spec.ts`, harness `test-harness/audit.tsx`); session-expiry test and installation-test analysis recorded in convergence.md.
- [x] Hosted CI on the pushed branch: run 43583023514 (`d62db6a`) failed one real-stack Playwright locator (strict-mode match of two status messages); test-only fix `821cc17`; run 43584841853 (`821cc17`) passed every job, including real-stack Playwright (see convergence.md).
- [x] Review blocker fixed (local, then pushed): the function enforces the recent window itself (`p_end` within 60 s before / 5 s after the database clock); restricted-role PostgreSQL test with mutation checks.
- [ ] Owner review (outstanding, not claimed). *(Historical wording; PR #35 has since been merged. This file records no owner review or acceptance, and independent verification is not done.)*
