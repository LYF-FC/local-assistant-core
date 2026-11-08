# 020 — Current-user synthetic draft preview and review acknowledgement

Outcome: an explicitly opted-in authenticated user with current workspace access can preview one live draft and explicitly acknowledge its exact revision/content hash. This records a prepared review, not a business-state confirmation or execution approval. Actual draft confirmation/creation/correction/forget API writers remain absent.

POST preview/review uses existing HTTPS/Host/Origin/session/user/CSRF/workspace transaction authority before file/connection access. Separate opt-in flag and explicit scoped grants are required; default POC stays disabled. Reuse verified restricted login/NOLOGIN role/OID/endpoint and fresh per-request engine disposal; no owner/administrator credential in API.

Review body allows only expected_revision, reviewed_hash, request_id and explicit decision approve. Server selects snapshot/hash/actor/session/time. Lock current row FOR SHARE, recheck source/expiry and maintain registry authority through both commits. Return immutable snapshot metadata, execution/confirmation false. The preview is not a reusable permission token.

Migration 0011 adds private prepared reviews with server ID/time/five-minute expiry, actor/session, record revision/hash and scoped request idempotency. Identical current-session replay revalidates authority/current record and returns the existing receipt; conflicting or expired request is rejected. A work preparation may remain if later identity commit fails; future consumption requires committed identity evidence plus fresh authorization/revision/source/expiry and one-time semantics. No consumption or confirmation writer is delivered.

Review payload hashes must be scrubbed atomically when the draft is forgotten; immutable minimal audit stores no payload hash. Restrict review updates to exact hash-null redaction after parent forgetting; delete/truncate denied. Existing history/tombstone redaction and recovery limits remain. No real employer data, model, key, export, capture UI or new dependency. All data stays local.

Acceptance: strict malformed/spoofed body rejection; unauthorized/CSRF/unassigned requests never open storage; current restricted-role preview/review, replay/conflict/stale/source/expiry/session/grant failures; row/revocation waits and independent commit/audit failures; hash redaction/rollback/restore; default-disabled TLS/browser and unchanged lifecycle/capture gates. Final exact-head CI before readiness.
