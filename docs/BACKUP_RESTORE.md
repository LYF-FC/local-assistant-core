# Backup and recovery contract

Target: local-SSD PostgreSQL with encrypted, versioned backups to Nice and an independent Paris copy. Original files, configuration, migrations, keys, workflow definitions and model manifests need coordinated recovery. RAID and a writable mirrored share are not backups.

## Current evidence

CI performs a synthetic logical database dump/restore in a disposable PostgreSQL service. It checks schema and a sentinel record after restore. No household backup jobs, encryption keys, off-site access or scheduled production backups are configured in this increment.

## Production runbook requirements

- Agree RPO/RTO, then choose dump cadence and WAL/PITR if required.
- Use least-privilege backup identities, encryption, retention and immutable/offline copy; keep key recovery independently protected.
- Record backup start/end, database/schema version, file manifest/checksums, outcome and freshness; alert independently on overdue backups.
- Restore to a separate isolated host/database before validating; never overwrite the only live copy.
- Recover configuration/keys, apply the matching application version, restore DB and originals, validate counts/checksums/permissions and reconcile unfinished jobs.
- Disable sending/device writes during recovery until operation IDs and connector cursors are reconciled to avoid duplicate actions.
- Time a full cross-site rebuild and record actual results before approving production.

Schema downgrades in tests are not a production rollback strategy. Back up before migrations; favor compatible expand/contract changes and roll-forward repair. A previous image may be incompatible with a changed schema.

## Identity recovery requirement

0002 adds password hashes, token/CSRF digests and persistent rate windows to the protected database. Treat all as sensitive backup content. Before exposing a restored database, keep the API stopped and revoke every restored session under the trusted DB-administration recovery procedure. Spec 037 supplies a reviewed global batch CLI in [RESTORED_SESSION_QUARANTINE](RESTORED_SESSION_QUARANTINE.md), including non-Work users; its final clear-at-commit result is not permission to restart services. Otherwise a previously revoked session may be resurrected by an older backup. CI checks the 0002 schema restore with synthetic data; operational revocation/key/host recovery is a separate acceptance gate.

## Audit/approval guards and runtime grants

0003 restores protected audit/state functions and triggers as well as records. Restore through the trusted owner/migration path, verify sentinel records and mutation rejection, and then re-provision reviewed runtime grants using a distinct runtime secret. Runtime credentials cannot restore/disable guards. PostgreSQL roles are cluster objects and need explicit recovery provisioning; they are not assumed to be embedded in a database-only dump. Revoke restored sessions and reconcile pending/consumed approvals before real actions are ever enabled.

Jobs/outbox recovery: include durable_jobs and job_outbox with approvals and audit. CI preserves a synthetic interrupted lease across restore. Keep workers/dispatch disabled after restore pending authority/session review and external reconciliation; see DURABLE_JOBS.md.

Spec 007 recovery: back up memory_records and memory_revisions with audit/identity. A post-forgetting snapshot must restore with scrubbed current/history payload. Older backups can reintroduce forgotten data: retrieval/inference must remain disabled until post-backup forgetting decisions are reconciled. Independent retention/expiry and durable deletion reconciliation are not completed production features. See SCOPED_MEMORY.md.

## Synthetic login recovery boundary — 2026-11-05

Spec 016 managed work logins are cluster-global and are not included in ordinary database logical dumps. The restore suite does not recreate credential verifiers, enable workspaces or activate a provider. A new database OID changes the derived role/login identities. Keep restored consumers disabled and review independent secret recovery, reissue and pool/session revocation before activation. See WORK_CREDENTIAL_LIFECYCLE.md.

## Protected-file volume recovery boundary — 2026-11-05

The optional spec 017 secret volume contains plaintext protected by filesystem permissions; do not add it to general archives or treat logical DB restore as credential recovery. Keep restored workspace/adapter disabled, review OID/roles and password-manager/reissue/session state, then explicitly prepare/activate a fresh bundle. No full-host/secret-restore acceptance is delivered by the hosted synthetic overlay. See WORK_SYNTHETIC_ADAPTER.md.

## Work forgetting restore contract — 2026-11-05

Spec 018 specifies a future work-only suppression ledger reconciled before restored content/indexes become readable. The in-memory forget projection does not update any ledger or erase backups. Persistent historical redaction, derived-copy purge/export tracking, chosen backup expiry and independent document-key recovery remain required before content capture. See WORK_LIFECYCLE_CONTRACTS.md.

## Persisted drafts after-forget restore — 2026-11-05

Migration 0010/current/history/audit/tombstone state is included in the logical restore sentinel. A dump taken after forget preserves null draft histories/tombstone; independent source objects remain. This does not suppress payload restored from a backup older than the deletion, erase prior exports or recover document keys. Newer external suppression reconciliation and host/key acceptance remain #5/#25. See WORK_DRAFT_PERSISTENCE.md.

## Prepared-review hash recovery — 2026-11-05

Migration 0011 stores content hashes only in private scrub-capable preparations, not immutable audit. Draft forgetting clears those hashes atomically. The after-forget dump/restore sentinel checks live and null-hash preparations, metadata audit, RLS/copy-role denial and existing draft tombstones. Old client responses, original sources and older-backup suppression/key recovery remain separate gates. See WORK_DRAFT_REVIEW.md.

## Synthetic Work expiry reconciliation — spec 030

The manual disabled-workspace cleanup procedure in [WORK_RETENTION](WORK_RETENTION.md) redacts expired current/history/party/request/review payloads atomically with a completion receipt. The logical restore sentinel verifies the disabled state, redactions, retained live control and receipt from a post-cleanup dump. This neither prevents resurrection from older backups nor reconciles a newer independent suppression ledger, stale restored grants/sessions, document keys, derived stores or downloaded exports. Restored Work stays quarantined pending applicable recovery gates. Migration 0016 refuses downgrade when retention evidence exists.

## Reviewed synthetic Work restore quarantine — spec 031

Spec 031 adds a manual reviewed quarantine step after isolated logical restore inspection. Explicit target, workspace disable, grant removal and revocation of all current grantees’ platform sessions commit with a metadata receipt. The restore drill copies a synthetic active session and verifies it stops resolving afterward, while private content/redactions stay unchanged. This is neither automatic startup enforcement nor older-backup suppression; applicable credentials/keys/jobs/source/derived/export/full-host gates still precede activation. See WORK_RESTORE_QUARANTINE.md.

## Older-backup forgetting reconciliation — spec 032

Merged prior implementation review/spec 032 tests a real pre-forgetting dump with a separately exported newer terminal-decision file, then quarantines and reconciles that older restored snapshot. Current/history/party/request/hash redactions and receipt are atomic; live control survives and Work stays disabled/no-grant. A manually supplied metadata digest is not authenticated/latest-complete proof, and absent IDs acquire no durable ban. Independently protect/verify the latest applicable ledger; full-host/keys/credentials/derived/unmanaged copies remain open. See WORK_BACKUP_SUPPRESSION.md.

## Authenticated Work recovery manifests — spec 033

Spec 033 requires authenticated suppression files in the normal CLI, anchored by a separately retained workspace key and independently trusted public fingerprint. The synthetic old-backup drill removes its primary key file and recovers a separate copy outside the database dump before authentication/reconciliation. This is not physical off-site/hardware key recovery, encryption, revocation/latest-completeness or full-host acceptance. See WORK_MANIFEST_AUTHENTICATION.md.


## Known checkpoint and pending Work input — specs 034/035

Merged prior implementation review requires the independently retained source export hash for normal authenticated manifest verification/reconciliation; see WORK_MANIFEST_AUTHENTICATION.md. Merged prior implementation review/spec 035 separately discards restored pending captures/corrections/forget/confirmation requests and cached review hashes after quarantine, preserving retained notes/parties/sources and completed outcomes. Migration 0018, exact target/plan/time, bounded all-or-nothing effects, immutable metadata audit and downgrade refusal apply. Run it explicitly with services stopped; it does not reconcile global approvals/outbox or activate any consumer. See WORK_RESTORE_REQUESTS.md.


## Selected restored no-op authority — spec 036

After isolated restore and before restarting consumers, the merged prior implementation review [reviewed execution quarantine](RESTORED_EXECUTION_QUARANTINE.md) cancels selected outstanding no-op approvals and dead-letters selected queued/leased no-op jobs, clearing leases and rejecting old-token completion. Explicit target/scope/IDs, clean owner, current exact review and fail-fast table locks are required. Payloads, consumed approvals and completed/unselected history remain unchanged. No schema/grant change or automatic activation. This proves only selected coverage; full inventory, restored sessions/Work/credentials/keys, future external receipts and full-host acceptance remain separate gates.

## Global restored-session batches — spec 037

Merged prior implementation review global quarantine invalidates all current unrevoked platform sessions in freshly reviewed bounded batches, preserving already-revoked timestamps, credentials and other state. Every batch has its own exact target/time/hash and atomic receipt; replay cannot advance it. Copied non-Work active tokens and expired rows are covered by logical restore/container checks. Keep consumers stopped throughout remaining recovery; new sign-in remains possible with unchanged credentials after deliberate activation. No schema or automatic startup change. See RESTORED_SESSION_QUARANTINE.md.

## Consolidated recovery assessment — spec 038

Use [RECOVERY_ASSESSMENT](RECOVERY_ASSESSMENT.md) for an audited, non-mutating inventory, optional independently pinned checkpoint assessment, and the existing-tool operator sequence. Counts, caps and cross-scope work remain explicit; no report hash authorizes cleanup or startup. Staged real restore/container checks observe progress while deliberately retained work and independent acceptance gates remain visible. This grouped package does not replace actual full-host/off-site evidence.


## Discovery review inbox and selected digest — spec 045 candidate

Migration 0019 and its non-public fixed-search-path helpers are part of checked schema/role setup. The logical drill retains digest preparation metadata with its originating session retired and private grant removed; it stores no digest body. This tests preservation, not restored current authority, latest completeness or independent recovery. Existing global session quarantine and full-host/key/owner acceptance remain mandatory. See [review inbox guide](DISCOVERY_REVIEW_INBOX.md).
