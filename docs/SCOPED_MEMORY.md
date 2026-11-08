# Explicit scoped memory — development/test API

Spec 007 adds local structured entries, explicit preferences, correction history, expiry, bounded export and operational forgetting. API merged #28; the companion Memory UI is merged #29 and manual Discovery feedback #30 reuses this store. No inference, embeddings, automatic imports, work scope, model/provider or task permission is enabled. HTTPS/sign-in #27 supplies the Host/Origin/CSRF boundary. Use synthetic fixtures first.

## Data and authorization

Kinds: profile, preference, experience, procedure, context. Each entry has immutable owner (session user), scope, kind and creation time; mutable title, bounded JSON content, source type/reference, confirmed/tentative assessment and optional expiry; revision and update time. A context entry requires future expiry. Source references are untrusted text/opaque IDs, never automatically fetched or executed. A stored procedure/preference does not grant permission to use a tool or change policy.

Current assigned scope is mandatory on every request. member_a_private, member_b_private and finance_private also require ownership; assigning another user that scope does not reveal the first user's memories. household_shared, parents_child and member_business permit current scoped members to read active current entries. Only the owner can correct/forget or inspect snapshots, including shared entries. technical_admin is not a memory-content scope; no work_private/workspace support is implied. The API's SQL filters are the family data isolation boundary; this increment does not claim PostgreSQL row-level security or the separate work-role isolation of spec 005.

All successful reads/writes/exports and denials are minimally audited. No title, content, source reference or full snapshot is copied into audit. State and audit share a transaction; audit/commit failures roll back. PostgreSQL seals owner/scope/kind/creation, requires sequential revisions and protects historical payload from rewriting except forgetting scrubs. Runtime credentials have no DELETE/DDL; history UPDATE is limited to its snapshot column and trigger policy. Privileged owners can alter DDL; this is not an owner-proof archive.

## API contract

All requests use existing authenticated HTTPS/session guards. Unsafe requests also require exact Origin and X-CSRF-Token. No arbitrary owner, revision/state override or scope move is accepted in bodies.

| Endpoint | Contract |
|---|---|
| POST /api/v1/memory | scope, kind, title, content object, source_type (manual/document/conversation/feedback), source_reference, assessment (confirmed/tentative), optional timezone-aware future expires_at |
| GET /api/v1/memory | scope/kind filters; limit 1–50 (default 25), UUID after cursor; expired/forgotten excluded by default |
| GET /api/v1/memory/{id} | Current authorized entry; expired/forgotten returns metadata-only 410. Owner may explicitly inspect expired content using include_expired=true |
| PATCH /api/v1/memory/{id} | Owner supplies expected_revision and full replacement mutable fields; stale revision returns 409; appends a new snapshot |
| GET /api/v1/memory/{id}/history | Owner-only paged historical snapshots, integer after revision; history is never automatically eligible context |
| POST /api/v1/memory/{id}/forget | Owner + expected_revision; clears current content/provenance/assessment/expiry and every snapshot in one transaction, leaving a minimal tombstone |
| GET /api/v1/memory/export | Versioned JSON attachment, same authorization/paging/filtering; owner can explicitly include expired entries or forgotten tombstones |

Bounds: title 160 characters, source reference 512 characters, JSON 16 KiB with depth/collection limits. Private/missing IDs both return generic 404. Other scoped readers cannot inspect owner history or retrieve expired shared content through include_expired. Default current entries include eligibility/expiry flags; future context assembly must respect current scope/expiry and tentative labels, never blindly replay historical snapshots. No inference-generated fact can become confirmed automatically through this explicit-user API.

## Export, forgetting and recovery

Export schema_version=1 includes authorized current records, IDs/versions/provenance/timestamps and next_cursor. History has its own bounded endpoint. Follow pages explicitly; concurrent writes are not a guaranteed global snapshot. Exports remain private local data; do not commit them or upload them as general model context.

Forgetting is irreversible through the API: remove all operational payload/provenance from the record and revision snapshots; preserve only IDs, owner/scope/kind, timestamps, version/status and minimal audit required for reconstruction. Shared readers lose payload access. No derived index exists yet; any future index/cache must join deletion propagation and acceptance before it is enabled.

This does not erase old independent backups retroactively. Backup retention/expiry and a durable forgetting reconciliation record are required for full production deletion assurance. Before restoring an older backup, keep retrieval/inference disabled and reconcile forgetting decisions made after that backup; otherwise old content can reappear. The full-host/recovery gate remains open. CI verifies that a snapshot taken after forgetting restores with current/history content still scrubbed, alongside interrupted jobs and audit guards.

## Dependencies and next steps

This API is structured truth for later preferences/Discovery feedback; it does not itself rank proposals, build prompts or run a model. Add owner-facing inspect/correct/export/forget UI, derived-store deletion controls and validated local retrieval next. Work Companion requires its own explicit work/workspace schema/roles/index/context boundaries before accepting professional data. No production host or real data is used by development tests.
