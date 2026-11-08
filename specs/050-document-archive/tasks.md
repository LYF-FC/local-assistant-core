# Tasks and checklist

- [x] Descriptor-safe bounded archive adapter and explicit empty-root initialization.
- [x] Immutable binding model/migration/minimal runtime grants.
- [x] Two-phase audited owner capture, verification and fail-closed managed forgetting.
- [x] Responsive owner controls, validated status and stale-response clearing.
- [x] Unit/fault, actual PostgreSQL negative/lock and migration tests.
- [x] Archive-aware synthetic restore and browser coverage.
- [x] Canonical context/architecture/decisions/operations/setup/roadmap/register updates.
- [x] Required local checks and privacy review.
- [ ] Full exact-head hosted evidence: recorded in PR metadata before readiness, without an evidence-only source push.

Analysis: copying before a durable binding can orphan private content after SQL rollback. Binding and audit commit first, then reauthorize/copy. Deleting files before SQL commit is recoverable because original bytes remain in SQL; deleting after SQL commit could falsely report forgetting. All operations serialize document state before archive mutation. No directory object is authority to restore or disclose content.
