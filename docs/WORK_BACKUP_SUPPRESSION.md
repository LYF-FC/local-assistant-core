# Reviewed forgetting reconciliation into older synthetic Work backups

Merged prior implementation review/spec 032 replays supplied terminal forgetting decisions into a selected quarantined synthetic snapshot. A trusted operator exports a complete bounded metadata file from a newer disabled workspace, protects it independently, then reviews/applies it after restoring an older backup. Work stays disabled with no grants. No information leaves the private environment.

## Trust and prerequisites

Use development/test synthetic data only, with the explicit configured/actual database and clean READ COMMITTED storage/registry/audit owner. Test databases must be disposable `butler_test*` targets. The selected active technical-admin UUID is an audit reference, not HTTP human proof. Keep applications/workers stopped during recovery. Apply migration 0017 through the existing short-lived migration service; preserve users, CA, secrets and volumes. Never put owner credentials in API.

The file records all forgotten notes with matching tombstones and forgotten parties with matching immutable audit in one source workspace, at most 25 combined decisions. More decisions or inconsistent evidence fail without partial export. It contains schema/mode, export/workspace/operator UUIDs, source database OID, generation time and ordered kind/record UUID/forgotten revision/time entries. No note text, party label, source reference, token, credential or content-derived hash is copied.

**The inner digest is not authentication or proof of completeness.** It detects canonical metadata changes. Spec 033 now requires an authenticated version-2 envelope and an independently pinned workspace key in the normal CLI; follow [WORK_MANIFEST_AUTHENTICATION](WORK_MANIFEST_AUTHENTICATION.md) before export/recovery. Any holder of that symmetric key can forge a file or supply an older valid file. Source database OID is provenance, not portable cryptographic identity. Independently protect, retain and verify the latest applicable file before trusting its coverage. This tool does not maintain an automatic off-host ledger, prove that no newer decisions were lost, or certify full recovery.

## Export from the newer source

Disable the chosen source workspace using existing trusted administration. Use an existing protected local directory outside Git and general archives, mounted at `/recovery`, owned by the command UID (normal migration container: 10001). Directory access should be owner-only. Set `BUTLER_SUPPRESSION_DIR` to its absolute host path and use the intended source configuration.

```sh
docker compose --env-file SOURCE_ENV -f infra/core/compose.yml run --rm -T \
  -v "$BUTLER_SUPPRESSION_DIR:/recovery" \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys:ro" migrate \
  python -m app.work_suppression --environment development \
  --database SOURCE_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID \
  --recovery-key /recovery-keys/recovery-key.json \
  --expected-key-fingerprint TRUSTED_FINGERPRINT \
  export --output /recovery/manifest.json
```

Replace placeholders with actual synthetic configuration/IDs. Export exclusively creates a new 0600 regular file and fsyncs it and its parent; it never overwrites an existing path. The independent file is at most 32 KiB, owned by the command UID, without group/other permissions. Import also refuses symlinks, special files, hardlinks, changed reads, duplicate JSON keys, malformed/extra/duplicate/unordered decisions, bad digests and unsupported bounds. Keep ownership correct when transferring/mounting the file; do not relax permissions to make import succeed.

The database audit event is `admin.work_suppression_manifest_prepared`, committed before file persistence. It records export ID, metadata digest/count and selected operator, explicitly without proof of saving. Retain the successful stdout `checkpoint` record independently, including its `manifest_hash`; supply this trusted hash to offline verification and target preview/apply. Never adopt it from a candidate file or restored database. Export rejects `--expected-manifest-hash`. Successful command output says the local file was saved, not independently backed up. A write/durability failure may leave only preparation audit. Inspect file/receipt state before deliberate retry to a new path. Separately copy and verify the file under the reviewed recovery/key policy; the CI temporary copy is synthetic evidence, not an owner backup.

## Restore, quarantine, preview, reconcile

Restore the older snapshot offline and upgrade its schema. First follow [WORK_RESTORE_QUARANTINE](WORK_RESTORE_QUARANTINE.md): disable the selected workspace, remove all its grants and revoke affected restored sessions. Import requires disabled/no-grant state under the registry lock. Other workspaces require separate handling.

Mount the protected file read-only using the restored configuration:

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T \
  -v "$BUTLER_SUPPRESSION_DIR:/recovery:ro" \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys:ro" migrate \
  python -m app.work_suppression --environment development \
  --database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID \
  --recovery-key /recovery-keys/recovery-key.json \
  --expected-key-fingerprint TRUSTED_FINGERPRINT \
  --expected-manifest-hash TRUSTED_MANIFEST_HASH \
  preview --manifest /recovery/manifest.json
```

Review target database name/OID, workspace/operator, manifest digest, current record states/revisions, linked pending changes/confirmations/review IDs and issue time. No content/hash value is shown. A live target at or above the source forgetting revision is a lineage conflict; obtain/review correct evidence rather than editing the file to force deletion. Missing/already-forgotten records are reported. At most 100 linked effects and 32 KiB plan are allowed. Do not truncate/edit the ledger or bypass caps; use a separately reviewed procedure for larger recoveries.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T \
  -v "$BUTLER_SUPPRESSION_DIR:/recovery:ro" \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys:ro" migrate \
  python -m app.work_suppression --environment development \
  --database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID \
  --recovery-key /recovery-keys/recovery-key.json \
  --expected-key-fingerprint TRUSTED_FINGERPRINT \
  --expected-manifest-hash TRUSTED_MANIFEST_HASH \
  apply --manifest /recovery/manifest.json --issued-at PREVIEW_ISSUED_AT \
  --reviewed-hash PREVIEW_HASH --decision reconcile_restored_suppressions
```

Copy the exact issue time/digest. Apply recomputes the metadata plan and requires a match within five minutes, including final write. A manifest's historical decisions do not expire, but it cannot certify current completeness; future timestamps are refused. Changed manifest, target, grant/operator/record/dependency state rejects. Replayed plans cannot advance work or append another success receipt. A fresh all-absent/already-forgotten plan with no linked effects is a no-op and cannot produce a completion receipt or durable absent-ID deletion ban.

## Atomic effects and recovery boundary

Existing lifecycle forgetting erases selected note current/history/owner/source payloads, review hashes and bound pending corrections; party forgetting clears labels. All pending bound note changes (including forget requests) are denied/redacted, and pending confirmations are denied, including orphan confirmation metadata. Unrelated notes/parties, original sources and unbound captures stay unchanged. Local target terminal revision follows its own contiguous history; it need not equal the newer source's terminal revision.

Migration 0017 narrowly permits terminal forgetting by the clean owner in explicit restore mode, on disabled synthetic workspaces with zero grants and READ COMMITTED isolation. Guards fail closed on NULL predicates. Ordinary roles, normal active operations and expiry maintenance retain their boundaries; no new API grant, table, dependency or service is added. Registry locking precedes row changes; timeouts/audit/guard failures roll back. Downgrade refuses `admin.work_suppression_applied` evidence and requires reviewed recovery.

Private audit/tombstones, linked redactions and metadata-only completion receipt commit together. The receipt stores selected operator, export ID/time, manifest/plan metadata digests, outcome IDs/previous states, linked counts and receipt UUID. No public audit is treated as bearer authority or a reason to skip current data checks. Output follows commit. After uncertain commit, inspect current metadata and receipt, then generate/review a new plan. Receipt always reports disabled, zero grants and `recovery_complete=false`; it never enables or regrants Work.

This reconciles only supplied decisions into this snapshot. Newer lost decisions, absent-ID resurrection through future imports, original sources, unbound captures, credentials/keys, other restored workspaces/jobs/approvals, derived stores, downloaded exports and timed independent full-host recovery remain separate gates. No actual M2, real employer-content or complete issue #5/spec 005 acceptance is claimed.

## Verification

The logical restore drill takes a real pre-forgetting dump, then forgets the newer source rows and exports their real terminal decisions into a separate protected file. It restores the older live/unexpired rows, verifies a copied active session, quarantines the workspace, and applies the newer file. It verifies note/history/party/request/hash redaction, unchanged live control, disabled/no-grant state, session denial and receipt. Container smoke independently runs CLI preview/apply/replay and exports real terminal rows. Existing migration/negative/concurrency/RLS/TLS/browser/security gates remain required; no UI or new visual acceptance is added.

Spec 033 authenticates these files using a separately recovered key and independently pinned public fingerprint; see [WORK_MANIFEST_AUTHENTICATION](WORK_MANIFEST_AUTHENTICATION.md). Authentication does not establish latest completeness, encryption or full-host recovery. Unsigned legacy files require verified source re-export for normal CLI import.

Spec 034 requires a separately retained known source checkpoint hash before target database access. Matching authentic older files remain possible only when their own checkpoint was deliberately trusted; this is not latest completeness. Previously retained trusted prior implementation review hashes remain compatible. See WORK_MANIFEST_AUTHENTICATION.md for lost-checkpoint handling and trust limits.
