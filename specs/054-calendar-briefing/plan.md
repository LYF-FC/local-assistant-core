# Plan and analysis

Preserved calendar/MVP contracts retain original provider IDs, timezone-aware recurrence, conflict visibility, manual-import fallback and later reviewed writes; spec 007 is a historical boundary, not delivered connector evidence. This increment implements the normalized read/reconciliation and deterministic briefing boundary without choosing/activating a provider. ORG-05 mirror is distinct and unchanged; ORG-03 recurrence delivery is not recurrence identity. Installation-local source UUIDs and stable software scope keys keep later INSTALL migrations explicit; fixed household membership is not generalized here.

1. Add bounded calendar source and sealed full-snapshot revision tables, migration, restricted grants and quota locking; retain existing core schema/authorization helper.
2. Validate/canonicalize normalized complete windows; reconcile identities/versions/coverage atomically with metadata audit and replay semantics. Preserve last-good data on failures and scrub on forget.
3. Compose a read-only day briefing using current scoped calendar snapshots, tasks and confirmed memory references; bound and disclose coverage, staleness, truncation and possible overlaps.
4. Build strict client receipts, ephemeral calendar/briefing UI, JSON preview/import and owner history/export/forget controls; no provider URL/secret settings.
5. Focused tests during development, one final make check/security/privacy sequence, actual PostgreSQL/migration/recovery and HTTPS browser evidence. Backend/permissions/schema changes require full CI under existing selector. One coherent commit/PR/push; exact-head evidence in PR metadata; never auto-merge.

Constitution review: deterministic authority, local data, current grants and commit-before-release audit preserved. Bounded normalized imports add no parser/network/model attack surface. Migration adds protected JSON snapshots to existing logical backup; no external storage or new key state. Quotas bound retained history but long-term compaction/retention policy remains open. Real-provider correctness and host acceptance remain unclaimed.
