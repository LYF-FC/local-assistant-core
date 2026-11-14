# 072 tasks

Status of each item is a local-branch fact only. Nothing is verified, merged or accepted.

- [x] Contract: spec.md (this directory).
- [x] Migration 0037 adds `butler_audit_summary(text, timestamptz, integer)` (actor derived in-database from the live session token); downgrade drops it.
- [x] `runtime_role.configure` grants EXECUTE on the function and still grants no audit SELECT.
- [x] Backend `operations.audit_summary` and `POST /api/v1/operations/audit-summary`.
- [x] Frontend strict parser, explicit-load section in the Operations overview.
- [x] Tests: unit (auth, shape, validation, audit-failure), PostgreSQL integration under the restricted runtime role (counts, exclusions, denial, function guards, migration round-trip), Vitest, mocked browser spec.
- [x] Documentation: OPERATIONS_OVERVIEW.md, FEATURE_REGISTER OPS-10 note, PROJECT_MASTER, convergence.md.
- [x] Pre-push review remediation (local): actor substitution closed (UUID parameter replaced by session-token binding; restricted-role PostgreSQL substitution test); component-level browser tests for the audit section (`browser/audit-summary.spec.ts`, harness `test-harness/audit.tsx`); session-expiry test and installation-test analysis recorded in convergence.md.
- [ ] Owner review (outstanding, not claimed).
