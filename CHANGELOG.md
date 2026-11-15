# Changelog

## Unreleased

Historical record of changes. Entries before spec 068 were not kept here; merged work from PR #1 onward is indexed in [PROJECT_MASTER.md](PROJECT_MASTER.md#5-stage-and-gate-progress), which owns current status. Nothing here implies a release or MVP acceptance.

- Spec 074 (implementation merged in PR #40, no migration; frozen specification PR #39, documentation only): synthetic-only offline recovery-set manifest tool, `python -m app.recovery_set generate|verify`, with an HMAC-authenticated manifest, independently supplied trust inputs, closed-set enumeration, atomic no-replace publication and an extended synthetic restore drill. Owner-accepted for the synthetic-only Phase B scope on 15 November 2026; no real key, recovery set or recovery-readiness claim. See [docs/RECOVERY_SET.md](docs/RECOVERY_SET.md).
- Spec 074 Phase C design/preparation package (documentation-only PR #42, merge `b081c12`): five draft documents covering key custody/key-generation requirements, expected-hash governance, retention/forgetting and capacity validation, plus a blank independent-verification template. Drafts remain proposals, not owner decisions; the subsequent implementation authorization is recorded separately.
- Spec 074 Phase C non-operational implementation (PR #43, merge `708e8134098846a40e0c49cae5a954913aef9fdb`): bounded C1–C5 record validators, report-only reconciliation, model-only capacity calculation and interface definitions. No real-key/key-management tooling or operations, NAS/production-storage access, capacity measurement, synthetic-key governance/capacity test, operational recovery or readiness claim. C1–C5 remain open; no independent verification, Phase C owner acceptance or wider gate/status promotion.
- Project-status reconciliation (documentation-only PR #41, merge `c77b808`): reconciled project master, decision and roadmap/status views after PRs #38–#40 and Phase B acceptance; no gate or register status promoted.
- Spec 073 (merged in PR #37, migration 0038): explicit, audited, queue-level overdue and stalled work observation for technical administrators; the contract was PR #36 (documentation only).
- Spec 072 (merged in PR #35, migration 0037): explicit, audited, count-only summary of security and administrative audit events, a first slice of OPS-10.
- Spec 071 (merged in PR #34): explicit attention inbox for one granted scope; the contract was PR #33 (documentation only).
- Spec 070 (merged in PR #28): calendar recurrence, synthetic provider-mode sync and briefing v2. PR #27 was a design proposal only; no implementation.
- Spec 069 (merged in PR #26): synthetic-destination invoice filing execution (migration 0034): separate exact owner request consumed atomically at the first claim, destination policy `destination-v1`, single claimant, reconcile-before-retry, no overwrite, forgetting that scrubs keys and history snapshots. No real filesystem, connector or provider.
- Spec 069 follow-up (merged in PR #29, no migration): `finish` and `reconcile` apply a result only to the exact row revision their own claim produced (locking read `WHERE revision = fence`), so a stalled worker or reconciler can no longer modify a newer attempt, append history or cause a false `failed`; PostgreSQL stale-worker, journey (twice-forwarded offline email to a filed synthetic entry, crash-boundary recovery) and migration 0034 downgrade tests; documentation corrections and a destructive-downgrade warning. MVP-03 stays incomplete; no real destination.
- Spec 068 (merged in PR #24): synthetic-channel notification path (migration 0032, owner-only read API, restricted worker). No real provider.
- Spec 068 corrections (merged in PR #25): paused deliveries are parked once instead of re-selected every pass, and migration 0033 validates every notification history snapshot field.

## Initial public-source candidate

Clean development source snapshot. No previous private history or public release claim is imported. See PUBLICATION.md and docs/VALIDATION.md.
