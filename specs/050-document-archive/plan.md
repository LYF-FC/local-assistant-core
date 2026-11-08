# Plan, analysis and dependency boundary

1. Implement a small local directory adapter with explicit provisioning, root identity, descriptor-relative bounded IO, locking and durable publication. No arbitrary path API and no production mount.
2. Add immutable document/root bindings in migration 0023; restricted runtime gets SELECT/INSERT only. A pre-copy committed binding makes filesystem cleanup obligations survive partial failure/configuration changes. DB originals are retained to avoid pretending filesystem and SQL commits are atomic.
3. Add audited owner-only prepare/copy and live verification endpoints. Preserve lock order/current authority. Extend managed forgetting to refuse missing roots and purge known files before SQL scrub. Failure outcomes are sanitized and retryable.
4. Add interface controls and strict response parsing; preserve all current document lifecycles and private defaults. Optional Compose override supplies a private development volume only when deliberately selected.
5. Test adapter faults, API negatives/transactions, real PostgreSQL locks/seals/migrations, browser disabled/available states and logical restore with independent archive directory copy. Finish required checks and privacy review before one completed batch push/PR.

No constitution conflict: deterministic structured authority, local bytes, payload/revision-bound operations, audit-before-output and private isolation remain. No remote data leaves the environment. No new schema grants confer administration/content rights. Migration downgrade loses binding metadata; purge/decommission archive copies before any real downgrade. Existing installations and real namespace migration remain separately authorized.

PDF/OCR is deliberately a following dependency batch: parser isolation/resource budgets and provenance need their own contract after the storage failure/recovery boundary is established. No automatic collectors/workers/schedules or production runbook activation are added.
