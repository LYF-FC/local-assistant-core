# Authenticated synthetic Work recovery manifests

Merged prior implementation review/spec 033 adds authentication to the manual older-backup workflow. The normal suppression CLI now requires a separately protected workspace key and an explicitly supplied expected public fingerprint. Editing a file and recomputing its old digest is insufficient. Verification happens before database connection; existing owner/quarantine/review gates still apply. No information leaves the private environment.

## Key and trusted fingerprint

Create a new key only for the chosen synthetic workspace. Use a protected owner-only directory outside Git/general archives, owned by the command UID (normal migration container: 10001). Set `BUTLER_RECOVERY_KEY_DIR` to its absolute host path. Do not mount this directory in API or background services. Preserve existing users, CA, secrets and volumes.

```sh
docker compose --env-file SOURCE_ENV -f infra/core/compose.yml run --rm --no-deps -T \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys" migrate \
  python -m app.work_suppression_auth generate \
  --workspace WORKSPACE_UUID --output /recovery-keys/recovery-key.json
```

The generator itself is offline: it makes no database/provider connection. It generates 32 random bytes, exclusively creates a new 0600 file, and fsyncs file and parent. Existing paths are never overwritten. Output contains only key/workspace IDs, a public `fingerprint`, `material_returned=false` and `independent_recovery_proven=false`. Secret material is never a CLI argument, environment value or output. Protected key JSON is plaintext; permissions are not encryption or an OS/hardware secret store.

**Record the fingerprint from trusted generation separately from the database, key file and manifest.** Obtain the expected value from that independently trusted record during recovery. Do not copy it from an untrusted artifact, database receipt or newly supplied key file to make a check pass. A substituted key/manifest pair must not be allowed to establish its own trust anchor. The fingerprint is public and may be recorded; it is not the secret or a bearer permission.

Independently protect/recover the key under the reviewed encrypted/off-site key policy; the current CI test copy is not owner-host acceptance. A missing key fails closed. Keep key material out of database dumps, general archives, logs, version control and screenshots. Do not reuse adapter login credentials or document encryption keys: the schema/domain here is specifically synthetic suppression authentication.

## Independently retained source checkpoint — spec 034

A valid old file can authenticate under the same key while omitting later decisions. Retain the successful source export stdout `checkpoint` record independently from candidate files and database dumps. It contains schema/mode, workspace, export ID/time, manifest hash, count and public authentication references. Its hash covers the complete canonical manifest body. Source output does not prove independent retention or latest completeness.

Offline verify and normal preview/apply now require `--expected-manifest-hash TRUSTED_MANIFEST_HASH`, using the known source checkpoint. Missing, malformed or mismatched hashes fail before database connection. Never extract this expected value from the candidate file or restored receipt to make verification pass. Export rejects the flag because its output checkpoint is not known in advance. A previously retained trusted prior implementation review export hash is compatible; neither format migration nor re-export is required solely for this policy.

A deliberately selected older trusted checkpoint can still match its own file. This comparison identifies a known checkpoint, not a globally latest ledger. If no independently trusted checkpoint survives, obtain a verified source export or use a separately reviewed exceptional recovery; there is no automatic trust adoption. Compare checkpoint workspace/export/time/count/key references as part of review, and keep restored Work disabled until the broader recovery gates pass.

## Offline verification

A recovered file can be checked before bringing up a database. Use the independently trusted fingerprint, with key/manifest directories mounted read-only:

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm --no-deps -T \
  -v "$BUTLER_SUPPRESSION_DIR:/recovery:ro" \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys:ro" migrate \
  python -m app.work_suppression_auth verify --workspace WORKSPACE_UUID \
  --recovery-key /recovery-keys/recovery-key.json \
  --expected-key-fingerprint TRUSTED_FINGERPRINT \
  --expected-manifest-hash TRUSTED_MANIFEST_HASH --manifest /recovery/manifest.json
```

Output shows public key/manifest references, export ID/time and decision count, with `recovery_complete=false`; it returns no key material or MAC. The checkpoint context confirms the supplied independently retained hash; separately assess latest-ledger coverage. Authentication alone cannot establish freshness or completeness.

## Export and reconcile

Follow [WORK_BACKUP_SUPPRESSION](WORK_BACKUP_SUPPRESSION.md) for newer disabled-source export, older offline restore/quarantine, exact review and atomic redaction. Add a read-only key mount and both global arguments to every `app.work_suppression` command:

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

Use the intended restored configuration/database for preview/apply, with both directories mounted read-only, adding the required global `--expected-manifest-hash TRUSTED_MANIFEST_HASH` before `preview` or `apply`. `TRUSTED_FINGERPRINT` is the 64-character value from the independent trusted record, not an automatically discovered file field. The workspace UUID, key ID and fingerprint must all match. Unsafe ownership/modes/links/special files, oversized/malformed headers, missing/wrong keys, namespace/pin mismatch, bad authentication and unsigned input fail before database connection. Do not loosen file permissions to fix an ownership mismatch; provision the appropriate command UID.

Authenticated version-2 files wrap the unchanged bounded version-1 metadata manifest with algorithm, key ID/public fingerprint and full MAC. No secret enters the manifest. Plans and receipts bind checkpoint mode/hash as well as public authentication references alongside existing manifest/target/dependency metadata, so changing key context invalidates the review. Receipts store those public references, not MAC or key material. Source audit records requested authentication and preparation only; it is not proof that a file was saved/backed up. Shared audit is never an independent cryptographic release certificate.

The normal CLI rejects old unsigned version-1 files. Re-export from a verified newer source using the known key/pin. There is no blind `seal`/upgrade command or unsigned-bypass flag. If only unsigned legacy evidence survives, stop before reactivation and use a separately reviewed exceptional recovery procedure. Privileged internal Python primitives remain trusted owner operations, with `trusted_owner_input` metadata by default; they are not a security boundary against a database/host owner.

## Rotation and limits

For a deliberate new key, choose a new protected path, independently record the new fingerprint, and re-export from the verified source. Do not delete still-needed historical keys or automatically replace pins. Old files require their matching retained key and trusted anchor. Compromise, revocation, automatic rotation and recovery of lost trust anchors require a separately reviewed policy; there is no online key registry or provider activation here.

This is symmetric authentication to a known key. Any key holder can forge a file. It is not encryption, asymmetric signing, nonrepudiation, source/human-attention proof or a guarantee that the file contains every newer forgetting decision. Previously valid files can still be stale; spec 034 rejects them relative to the supplied trusted checkpoint, not an unknown latest export. Keep restored Work disabled/no-grant until latest-ledger completeness, credentials/jobs, document encryption keys, sources/derived/unmanaged exports, full-host and actual M2/real-content gates are separately verified. Every reconciliation receipt remains `recovery_complete=false`.

## Verification and primitive choice

The implementation uses Python's standard HMAC API with SHA-256/full tags and `compare_digest`, plus explicit `secrets.token_hex(32)` generation. Public fingerprint and artifact MAC use distinct domain contexts. These choices follow the primary [Python HMAC documentation](https://docs.python.org/3/library/hmac.html) and [secure token generation documentation](https://docs.python.org/3/library/secrets.html), checked 2026-11-06. No cryptographic primitive or dependency is added from scratch.

Tests cover protected key/manifest files, independent pin/namespace checks, substituted/rotated keys, metadata tampering with recomputed digest, tag/domain/algorithm/header/legacy failures, secret masking and rejection before DB access. Actual PostgreSQL CLI tests retain all quarantine/owner/atomicity boundaries and record public references only. The older-backup drill generates/pins a separate synthetic key, removes its primary file, recovers a separate copy outside the dump, and authenticates/reconciles the newer file after restore. Container smoke runs generation, key-copy recovery, export/preview/apply/replay. These are synthetic file-copy/logic checks, not physical off-site/hardware key recovery.

Spec 034 tests two real same-key source exports after the old dump: A contains one forgetting decision, B contains two. The source stdout B hash is retained before restore; authentic A is rejected without writes, then B reconciles the old snapshot. Container and unit/CLI tests cover missing/malformed/mismatched hashes and checkpoint-context review invalidation. No schema, key or envelope format changes.
