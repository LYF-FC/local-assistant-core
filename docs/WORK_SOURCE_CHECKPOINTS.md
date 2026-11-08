# Retain source-withdrawal evidence and reapply it to an older backup

An older backup can restore an active source flag and the note/history/unsaved copies derived from it. This procedure exports selected **committed source-withdrawal decisions** into a protected authenticated metadata file, verifies it offline using separately retained trust anchors, and reviews/reapplies those supplied decisions on a disabled synthetic target. The existing [manual source-withdrawal procedure](WORK_SOURCE_WITHDRAWAL.md) and its guards remain unchanged.

This is a selected checkpoint, not an automatic latest-complete ledger. It does not delete original files, prevent future absent-ID imports, encrypt backups or authorize activation. All reports keep recovery/activation completeness false. No network destination, remote synchronization, model or provider is introduced.

## 1. Export from the known newer source

Keep consumers and other trusted maintenance stopped. Require a disabled synthetic workspace with zero grants. Select 1–10 sorted unique registered source UUIDs that are already inactive and have **no remaining current/history/pending derivatives**. Each must have a successful committed `admin.work_sources_withdrawn` receipt; an inactive flag alone is insufficient. The exporter includes the latest matching receipt ID/time available in this source snapshot for each selection, not a proof that no later decision exists elsewhere.

Use the separately retained workspace recovery key and its independently pinned public fingerprint from [key setup](WORK_MANIFEST_AUTHENTICATION.md). The existing key format remains compatible. Source files use distinct purpose, digest and HMAC domains; they cannot be substituted for note/party suppression manifests, or vice versa. Any holder of the symmetric key can forge evidence. Keep the key independently protected; HMAC does not encrypt the metadata.

```sh
python -m app.work_source_checkpoint export --environment development \
  --database KNOWN_NEWER_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID --source WITHDRAWN_SOURCE_UUID \
  --recovery-key /protected/workspace-key.json \
  --expected-key-fingerprint INDEPENDENTLY_PINNED_KEY_FINGERPRINT \
  --output /protected/new-source-checkpoint.json
```

Repeat `--source` for additional selections. The file contains workspace/source/export/operator UUIDs, original withdrawal receipt IDs/times, source database OID provenance, generation time, digest and HMAC references. It contains no note markers, quotes, payloads, raw content hashes, passwords or key material. It is limited to 32 KiB. Protected owner-only regular-file I/O rejects unsafe files, final-component symlinks/hardlinks, oversized/duplicate JSON, overwrite and incomplete headers. Treat this governance metadata as private.

Preparation audit `admin.work_source_checkpoint_prepared` commits **before** exclusive file creation/persistence and records `file_saved_verified=false`. A file error may leave preparation audit but produces no success output and never overwrites an existing file. Inspect state before retrying to a new path. Successful stdout returns a public `checkpoint` record including `manifest_hash`; independently retain that record and the corresponding file under the reviewed backup policy. A local save is not independent retention. Never discover the trusted hash from a candidate file or restored database/audit.

## 2. Verify offline before opening the target

This command requires neither database configuration nor a database password:

```sh
python -m app.work_source_checkpoint_file verify \
  --workspace SYNTHETIC_WORKSPACE_UUID \
  --recovery-key /independently-recovered/workspace-key.json \
  --expected-key-fingerprint INDEPENDENTLY_PINNED_KEY_FINGERPRINT \
  --manifest /independently-retained/source-checkpoint.json \
  --expected-manifest-hash INDEPENDENTLY_RETAINED_SOURCE_MANIFEST_HASH
```

Key namespace/identity/pin, strict source purpose, HMAC and the explicit file checkpoint must all match. Unsigned files, note/party files, substituted keys, edited metadata with a recomputed plain digest and valid older same-key files under a different retained checkpoint refuse. Accepting an older file under its own deliberately trusted hash remains possible; signature/pin verification cannot establish that the owner chose the latest complete evidence. Lost anchors require separate trusted source review/re-export, not adopting values from the candidate.

## 3. Review the isolated older target

Follow [recovery assessment/quarantine](RECOVERY_ASSESSMENT.md), keep the restored server disconnected from normal traffic, and use the privileged maintenance environment. Require an explicit configured/actual database name/OID, clean READ COMMITTED owners, an active technical-admin audit reference and a disabled synthetic/no-grant workspace. Normal recovery verifies protected key/file/pins **before connecting**.

```sh
python -m app.work_source_checkpoint preview --environment development \
  --database REVIEWED_RESTORED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID \
  --recovery-key /independently-recovered/workspace-key.json \
  --expected-key-fingerprint INDEPENDENTLY_PINNED_KEY_FINGERPRINT \
  --manifest /independently-retained/source-checkpoint.json \
  --expected-manifest-hash INDEPENDENTLY_RETAINED_SOURCE_MANIFEST_HASH
```

The file is the sole source selection; recovery accepts no `--source` override. Every selected target source must already exist in that workspace. Missing/foreign sources refuse the complete operation; no silent subset, binding creation, source tombstone or absence/completeness certificate is supplied. Future imports/ID reuse still need separate review. A future-dated source export also refuses against the target database clock.

Review the **whole outer plan**, including source receipt provenance, source/target OIDs, verified public authentication/checkpoint references and nested `withdrawal` source flags, current/historical note IDs/revisions and pending/cache effects. Source OID is provenance, not portable cryptographic identity. Historical-only references conservatively cause whole-note forgetting. Existing limits of 25 notes/100 effects/32 KiB remain; overflow refuses all writes. The inner action hash is not returned.

## 4. Apply exactly that file-bound review

Use the same flags and file. The issued timestamp is the exact **`withdrawal.issued_at`** from preview; the reviewed hash is the **outer `reviewed_hash`**:

```sh
python -m app.work_source_checkpoint apply --environment development \
  --database REVIEWED_RESTORED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID \
  --recovery-key /independently-recovered/workspace-key.json \
  --expected-key-fingerprint INDEPENDENTLY_PINNED_KEY_FINGERPRINT \
  --manifest /independently-retained/source-checkpoint.json \
  --expected-manifest-hash INDEPENDENTLY_RETAINED_SOURCE_MANIFEST_HASH \
  --issued-at EXACT_WITHDRAWAL_ISSUED_AT --reviewed-hash EXACT_OUTER_REVIEWED_HASH \
  --decision reapply_source_withdrawals
```

Five-minute review, current target/authority, file digest/export/auth references and the complete current source/copy set are recomputed. Another authentic export with the same source IDs has a different outer plan. Changed/stale/replayed/no-op reviews refuse; no automatic retries. The existing source cleanup runs internally with its own fresh exact review. It forgets affected current/history, denies pending copies, clears review hashes and withdraws selected source flags. Unrelated controls remain.

Two receipts commit atomically with all effects: the actual `admin.work_sources_withdrawn` cleanup receipt and `admin.work_source_checkpoint_reconciled`, which links that receipt to the supplied file digest, source decision receipts, export and public key/pin references. Failure of the second audit rolls back the first receipt and every cleanup change. Inspect receipts/state before retrying an uncertain commit. Keep the workspace disabled/no-grant and preview again to inspect inactive flags and empty affected sets.

## Limits and evidence

Selected source evidence is distinct from [terminal-note forgetting evidence](WORK_BACKUP_SUPPRESSION.md). Retain fresh independent note/party checkpoints where needed; neither file implies that every workspace or latest decision is covered. Original files/immutable synthetic validation markers, other derived stores, unmanaged downloads, future imports, independent keys, full-host/off-site and actual M2 acceptance stay open. Trusted owner powers can later alter source activation; this is not a permanent startup fence. Supported registry/business writers retain the existing fail-fast locking; no new API/runtime grant/schema/dependency/service defaults are added.

The logical drill takes a real dump while source flags/notes/copies are live, then withdraws on the newer source and exports two real same-key authenticated files. It recovers a separate protected key copy, rejects the older file under the independently retained newer pin, reapplies the newer file to the older snapshot, verifies current/history/pending-copy redaction and both receipts, then preserves that state through another full dump/restore. A non-root container independently exercises protected export, configuration-free offline verify, exact file-bound reapplication of a simulated revived flag/pending copy, replay refusal and receipt binding. These synthetic engineering checks are not owner-host acceptance.
