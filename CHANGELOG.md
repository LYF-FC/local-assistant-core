# Changelog

## Unreleased

- Spec 069: synthetic-destination invoice filing execution (migration 0034): separate exact owner request consumed atomically at the first claim, destination policy `destination-v1`, single claimant, reconcile-before-retry, no overwrite, forgetting that scrubs keys and history snapshots. No real filesystem, connector or provider.
- Spec 069 follow-up (no migration): `finish` and `reconcile` apply a result only to the exact row revision their own claim produced (locking read `WHERE revision = fence`), so a stalled worker or reconciler can no longer modify a newer attempt, append history or cause a false `failed`; PostgreSQL stale-worker, journey (twice-forwarded offline email to a filed synthetic entry, crash-boundary recovery) and migration 0034 downgrade tests; documentation corrections and a destructive-downgrade warning. MVP-03 stays incomplete; no real destination.
- Spec 068 (merged in PR #24): synthetic-channel notification path (migration 0032, owner-only read API, restricted worker). No real provider.
- Spec 068 corrections (merged in PR #25): paused deliveries are parked once instead of re-selected every pass, and migration 0033 validates every notification history snapshot field.

## Initial public-source candidate

Clean development source snapshot. No previous private history or public release claim is imported. See PUBLICATION.md and docs/VALIDATION.md.
