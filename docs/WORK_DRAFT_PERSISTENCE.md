# Quarantined synthetic work draft persistence

Spec 019 adds migration 0010 and `app.work_drafts`, a trusted local development/test persistence primitive for synthetic draft creation, correction, confirmation, prepared reads and terminal forgetting. It implements the merged lifecycle contracts in a real PostgreSQL transaction. **No capture/record HTTP route, application writer, scheduler, real employer source, document key or general export is enabled.** The existing five content gates remain pending; standard POC adapter defaults remain disabled.

## Schema and privilege boundary

| Private work table | Stored data / invariant |
|---|---|
| retention_policies | Explicit workspace/policy UUID and bounded maximum age; immutable, no installed default |
| source_registry | Matching existing synthetic validation-source UUID and active state; workspace-composite FK, no marker copy |
| drafts | Current composite workspace/record identity, policy/revision/state/expiry and validated synthetic snapshot |
| draft_revisions | Ordered revision metadata and payload; append history, only exact terminal null-redaction allowed |
| draft_audit | Actor/workspace/record/revision/event/server time/database initiator; no marker/source list/owner/date/hash copies |
| draft_tombstones | Immutable workspace/record/forget revision/time; no payload or source associations |

All six tables have forced workspace RLS with an explicit trusted recovery-owner policy and no PUBLIC privileges. Ordinary storage provisioning grants no new domain SELECT or mutation privileges. Family runtime cannot access the namespace. CI grants read-only inspection to disposable workspace roles explicitly; there is no new operator grant command or application write credential. Those scoped inspection reads hide expired payload/history and check the current active sources of each historical snapshot independently, so correcting a note to a new source cannot reveal an old revoked-source revision.

The mutation helper requires an explicit existing psycopg transaction, matching development/test configuration (butler_test* for tests), typed metadata, clean session/effective identity, READ COMMITTED and the actual draft-table owner. Actor UUIDs are trusted local synthetic metadata, not verified human identity; database initiator is recorded separately. A scoped or family login cannot become a writer by supplying a workspace/actor UUID. The host/database owner remains trusted and can change database protections; this is not physical isolation or a hostile-owner security boundary.

## Supported operations and locks

Callers manage commit/rollback. `create`, `transition` and `read` return prepared values inside that transaction; none commits, opens an HTTP response or proves delivery. There is no installed content CLI. Tests/restore fixtures use only synthetic markers and explicit policies/source catalog entries. Example retention values in tests are not owner/employer policy approval.

- Acquire the existing registry shared advisory barrier before current/source row locks, with two-second lock/five-second SQL budgets. Reject dirty identities or wrong isolation before workspace access.
- Validate an active synthetic workspace and explicit stored policy. Server UUID/time are generated within the trusted storage adapter; snapshot identity/state/revision checks and server timestamps are enforced in the database.
- Lock current row, revalidate ordered history and compare expected revision; SQL compare-and-swap remains explicit. Concurrent same-revision corrections have one winner and one stale result, without duplicate history/audit.
- Lock selected active same-workspace sources in stable order through commit. Raw source-state writes take the registry exclusive barrier in a statement trigger before row locks, so revocation waits for supported readers/writers. Existing workspace/grant barriers remain unchanged.
- Corrections reset confirmation without extending retention or changing kind/policy/identity. Confirmation preserves the payload and requires selected active sources; calling the local helper is not a delivered human review interface or permission to execute an action.
- Owner/party references remain unknown: non-null owner IDs are refused until a reviewed workspace-party/assignment boundary exists. Due dates may remain unknown. No household user FK or inferred colleague assignment is added.
- Check read expiry before and after private prepared-read auditing. Raw scoped SQL visibility also checks expiry/source state. These database budgets are not an end-to-end network deadline, and a prepared return is not authority for delayed future response release.

## Database guards and atomicity

Current-row triggers enforce initial draft/revision, monotonic server timestamps, immutable identity/kind/policy, revision increments, non-extending retention, live mutation eligibility, source/policy checks and unchanged confirmation payload. Invalid snapshots, duplicate/missing/revoked sources and non-null owner references are rejected. Direct draft delete/truncate is unsupported.

An after-row trigger writes revision history and minimal audit atomically with every current transition. Forgetting first terminalizes/redacts current state, nulls all earlier revision payloads, inserts a null terminal history revision and creates its tombstone/event in the same transaction. History updates can only null a previously present payload after its parent is terminal, with every other history field unchanged. Audit/tombstone/policy UPDATE/DELETE/TRUNCATE are blocked. The live 100-revision bound permits one final forget revision (101).

Audit/revision/tombstone errors roll back the entire work transition. Caller rollback and connection closure before commit do not persist prepared objects. There is no automatic write retry or promise about an ambiguous network commit: a future application broker needs payload-bound idempotency/status reconciliation and both work/identity commit checks before exposing success. No SECURITY DEFINER write function or user-controlled GUC grants application authority here.

## Forgetting and recovery limits

Persisted draft forgetting clears every revision payload and the current marker/source associations/owner/due/expiry. Minimal revision/actor/time/identity metadata and tombstone remain. The original synthetic source catalog/validation record is a separate input object and is not deleted by forgetting a draft. Previously returned Python objects, external exports, documents, indexes, jobs and backups are not erased. No general derived store exists in this increment.

The restore test seeds a live draft and a confirmed-then-forgotten draft before dumping. It verifies live current state, null forgotten histories, minimal tombstone/audit, all six forced-RLS tables, copied source-role denial, separately granted destination inspection and immutable tombstone guard. This proves a backup taken after forget preserves that forget. A same-DB tombstone cannot suppress forgotten content restored from an older backup by itself. Independent newer suppression-ledger reconciliation, original-source retention, derived purge, document keys and full-host recovery remain #5/#25 gates.

## Deployment and next increment

After merge and green main, the normal HTTPS update/rebuild applies migration 0010 and preserves users/configuration/volumes. No new credentials, role-provision command, retention choice, model or POC installation step is needed. The new tables are empty outside explicit synthetic tests; no source, policy or real work note is automatically created. Downgrade removes this migration's private objects and data only; do not use destructive downgrade as an operational rollback for future live records.

Next is a separately reviewed current-human write/read broker with explicit source/party/review permissions and response/commit/idempotency semantics, followed by synthetic capture/retrieval and independent key/derived/restore acceptance. The existing optional credential adapter still executes only the fixed validation read, not these storage mutations.
