# 019 — Transactional synthetic work draft persistence

Status: implementation candidate in draft prior implementation review. Workspace recovered; migration 0010, trusted local storage, restricted-role/concurrency/failure tests and logical restore sentinels implemented. Expanded hosted CI passed 331 backend/170 PG/91 frontend/17 browser plus TLS/restore probes (run 42051553875). Final documentation-head CI is required before readiness.

## Outcome and scope

Persist the merged spec 018 synthetic lifecycle in private work storage: draft creation, immutable correction history, explicit confirmation, expiry-filtered reads and terminal forgetting with a minimal tombstone. Current row, revision/history, private event and tombstone changes must commit or roll back together. The record/actor/workspace UUIDs remain metadata, never proof of current human authority.

First persistence increment is a trusted local development/test storage primitive and restricted-role validation harness. No HTTP/capture endpoint, application write credential, employer source, real retention policy, model, scheduler, export file or external transfer. Existing validation read and optional credential adapter stay unchanged; five content gates remain pending. Any later human-facing writer requires a separately tested current-user/session/workspace/source/owner authorization adapter.

## Proposed private schema

| Object | Purpose | Required constraints |
|---|---|---|
| work.retention_policies | Explicit synthetic workspace/policy identity and maximum age | Composite workspace/policy identity; no default policy; immutable approved version |
| work.source_registry | Explicit synthetic source references and active/revoked state | Composite workspace/source identity; refer only to matching existing synthetic validation records; no family FK or marker copy |
| work.drafts | Authoritative current record | Composite workspace/record key; policy FK within workspace; checked revision/state/snapshot coherence; expiry; immutable identity/kind/policy/creation |
| work.draft_revisions | Per-revision payload and immutable metadata | Composite workspace/record/revision key; append-only except exact all-history redaction after terminal forgetting |
| work.draft_audit | Minimal private transition/read-prepared evidence | Workspace/record/revision/event/actor/server time/database initiator; no marker, source list, owner/date or payload hashes |
| work.draft_tombstones | Terminal suppression marker | Composite workspace/record identity, forget revision/server time; immutable; no payload/source associations |

Migration 0010 implements these private tables; see docs/WORK_DRAFT_PERSISTENCE.md for the exact owner-only helper and privilege boundary.

## Permission and transaction boundary

- Force workspace RLS on all new tables, with explicit trusted recovery-owner policy. Reuse database-OID/workspace-bound role identity; copied source roles must not read a restored database.
- Revoke PUBLIC privileges. Family runtime and existing workspace roles get no automatic new domain write grants. Prefer owner-only synthetic mutation primitives for the first increment; any explicit scoped inspection grants are read-only and provisioned separately/reviewably.
- Scoped reads must hide expired payload/history and records whose selected sources are revoked. Forgotten current rows/history contain only redacted/minimal metadata. Source/record existence and FK errors must not expose peer workspace facts.
- Supported mutation helper requires explicit matching development/test target (butler_test* for tests), clean intended connection identity, READ COMMITTED, bounded SQL/lock waits and the registry shared advisory barrier before row/source locks.
- Raw source-state changes take the exclusive registry barrier before row locks, including statement triggers for direct SQL. Lock selected active source rows in stable order through commit. No SELECT-then-act authority gap.
- Lock current record, compare expected revision atomically and revalidate source/owner references under current workspace. Concurrent same-revision corrections must produce one winner and one stale-write result without duplicate history/audit.
- Owner metadata in the first local harness is an explicit synthetic actor, not authenticated human provenance. Confirmation by a trusted test helper is not a delivered human review UI or execution approval.

## Lifecycle and failure rules

Create uses server record ID/time and explicit stored policy. Correct resets confirmation, preserves earlier snapshots and never extends retention or reclassifies kind. Confirm preserves payload and requires current selected sources. Reads and mutations check expiry at release; expiry does not imply immediate deletion of backups.

Forget is allowed after expiry and at the live-history bound. Atomically terminalize/redact current state; null every historical payload, remove source/owner/date associations and payload-derived hashes; append minimal history/audit/tombstone. Repeat terminal forget is safe; correction/confirmation cannot resurrect it. No retained immutable audit may copy removed content. Database guards must reject history/audit/tombstone edits, destructive truncate/delete and attempts to forge an allowed redaction into arbitrary replacement.

An audit/trigger/revision/tombstone failure must roll back the whole work transaction. No automatic write retry after uncertain commits; define a reviewed idempotency/status contract before application exposure. Work/identity transactions are not distributed atomic commits: future broker responses require both relevant commits and honest prepared-event semantics.

## Retention, exports and recovery limits

This increment must not install real retention defaults or document keys. No family/work cross-import, general export route or derived context/index/job is created. Physical file/index/export purge and independent document-key management remain future acceptance gates.

A tombstone stored in the same database survives a backup taken after forgetting; it cannot by itself suppress content resurrected from an older backup. Independent newer suppression-ledger reconciliation, restored-session revocation and derived-index rebuilding remain #5/#25 requirements before enabling real content. Do not claim whole-host, key or post-backup forgetting recovery from a logical restore test.

## Required completion evidence

Implement the migration/store, negative-path and separate-connection concurrency tests, restricted family/peer/source/expiry denial, fault injection and logical restore. Re-run all four Foundation CI jobs on the final implementation head. Engineering verification is separate from merged delivery; ROADMAP.md stays unchecked until user merge. Non-null owners are refused rather than treated as authorized parties.
