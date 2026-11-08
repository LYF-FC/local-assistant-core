# Durable local original archive — spec 050

## Specify

An owner can copy every retained bounded text/Markdown original to an explicitly provisioned private local archive, verify its exact bytes, retry interrupted copies and forget all managed copies. Existing local upload/replacement/search/review/citation/export remains usable without archive configuration. Data stays on local disk and PostgreSQL; no egress, model, parser, mail, NAS or production activation.

This closes a storage lifecycle slice of DOC-X01/02, CORE-03 and PLATFORM-01. Database originals remain authoritative and recoverable during this transition. PDF/OCR, moving originals out of BYTEA, live Synology, generated answers and independent older-backup suppression remain open and are not removed from scope.

## Clarify

- Preserve spec 048 limits and exact bytes: UTF-8 txt/md, 128 KiB, 32,000 characters, 50 versions and existing owner quotas. No new parser/dependency or larger upload bound.
- Owner-only archive write/status; current session/CSRF/transport/scope/owner/revision checks and database row locks precede filesystem access. Shared viewers/admin have no archive privilege.
- Explicit empty private directory initialization creates a schema/versioned random root identity. Reject symlink path components, foreign/nonprivate roots, links/nonregular files, unknown entries and mismatched root identities. Operate through directory descriptors; user filenames never form storage paths.
- Commit an immutable per-document root binding and audit before any content copy. Then reauthorize a second transaction and copy. A failed second phase leaves a safe binding/retry state; failed binding audit writes no originals. Binding survives disabling/repointing configuration and prevents forgetting while the correct root is unavailable.
- Store generated document-ID/revision filenames, private modes, fsynced temporary files, atomic nonoverwriting publication and directory fsync. Verify existing bytes for idempotence; never overwrite corruption. Bound each object at 128 KiB, each directory pass at 8192 entries and total archive payload at 64 MiB. Nonblocking process lock serializes capacity and file mutation. Forget can run at capacity.
- Status rechecks all expected versions against authoritative DB bytes and reports disabled/unarchived/partial/verified counts without filesystem paths or root identity. A successful result is a checked moment, not a backup certificate.
- Forget purges all matching originals and interrupted temporary copies before committing the normal DB scrub/audit. File failure rolls back DB forgetting; retry removes remaining files. DB commit failure can leave missing archive copies, repairable from retained originals. All writers take the document lock before archive lock; no background scan or cleanup of unknown objects.
- New revisions require explicit archive refresh. Correct/review still consumes versions; copying does not change document revision or attest review. Downloads continue through authorized DB originals, never arbitrary disk paths. Restored/unknown disk objects are never automatically ingested.

## Acceptance

Prove exact BOM/CRLF/Unicode originals/history, idempotence, restart/partial copy, quota/disk failure, corruption/link/path denial, binding audit failure, content/audit commit failure, deletion failure and retry, disabled/repointed root refusal, permissions/revocation/session expiry/current-revision waits, atomic binding seals/runtime role, migration roundtrip and actual logical DB plus separately copied archive restoration. UI must clear stale status on changes/scope/session/denial and suppress late responses. Required make/security checks, full disposable PostgreSQL suite, restore and full hosted CI gate must pass before readiness.
