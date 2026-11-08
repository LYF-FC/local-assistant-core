# Tasks and checklist

- [ ] Descriptor-safe bounded archive adapter and explicit empty-root initialization.
- [ ] Immutable binding model/migration/minimal runtime grants.
- [ ] Two-phase audited owner capture, verification and fail-closed managed forgetting.
- [ ] Responsive owner controls, validated status and stale-response clearing.
- [ ] Unit/fault, actual PostgreSQL negative/lock and migration tests.
- [ ] Archive-aware synthetic restore and browser coverage.
- [ ] Canonical context/architecture/decisions/operations/setup/roadmap/register updates.
- [ ] Required local checks, full exact-head hosted evidence and privacy review.

Analysis: copying before a durable binding can orphan private content after SQL rollback. Binding and audit commit first, then reauthorize/copy. Deleting files before SQL commit is recoverable because original bytes remain in SQL; deleting after SQL commit could falsely report forgetting. All operations serialize document state before archive mutation. No directory object is authority to restore or disclose content.
