# Reviewed synthetic Work source withdrawal and derived-copy cleanup

## Outcome
A trusted operator can select 1–10 registered synthetic source UUIDs in one disabled/no-grant workspace, preview every affected note and pending copy, then atomically withdraw their active bindings and forget the derived notes. Current and historical references count: a note corrected onto another source is still affected when a retained revision used a selected source. No private data leaves the local environment.

## Requirements
- Explicit configured/actual database name and OID, matching development/test environment, clean READ COMMITTED owners and active technical-admin reference. Try-lock the registry before fail-fast business table locks. Stop consumers and other trusted maintenance.
- Sorted unique explicit source UUIDs; reject missing/cross-workspace selections. Metadata only, no markers/text/payload/source labels/raw content hashes. At most 25 affected live notes and 100 linked pending/cache effects; refuse overflow without partial cleanup. Include pending new capture/corrections referencing selected sources even when no note yet exists.
- Exact five-minute server-issued plan binds target/operator/workspace/source active state, affected current note revisions, historical/current dependency flags and linked request/cache references. Reject changed/stale/replayed/no-op plans. No limit-driven partial withdrawal.
- Use the existing quarantined owner-only forgetting path: erase affected current/history content, pending note-change payload/hash and cached review hashes; deny all affected pending capture/change/confirmation requests. Leave unrelated notes, parties, sources, requests and workspaces unchanged.
- Only after redaction, set selected source_registry.is_active=false. Preserve source UUID bindings and append-only synthetic validation markers/audit. Source withdrawal is not original-file deletion or a cryptographic erasure claim. Existing owner powers may change source activation later; this tool never activates or repairs it. Forgotten notes stay terminal.
- Atomic cleanup/withdrawal/receipt. No schema, dependency, API/runtime grants or automatic action. Keep workspace disabled/no-grant and activation_authorized/recovery_complete false.
- An older backup can restore an active source flag; independent source withdrawal completeness, updated note-forgetting checkpoint, keys/originals/derived stores/unmanaged exports/other workspaces/full host remain separate gates. No recovery certificate.

## Acceptance
Real PostgreSQL coverage for current and historical-only notes, direct pending captures/corrections, cache/confirmation redaction, unrelated controls, exact plan/replay, overflow, authorization/target/isolation, rollback and lock contention. Prove withdrawn sources fail future note/capture validation after a separately controlled test activation. Actual CLI in logical restore and non-root maintenance container; full existing CI remains mandatory.
