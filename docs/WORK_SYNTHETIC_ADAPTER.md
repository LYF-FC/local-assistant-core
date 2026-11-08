# Optional protected-file synthetic work adapter

Spec 017 connects the merged bounded synthetic read broker to an explicitly opted-in local credential file. Standard install/restart/update remains disabled. No employer source, debrief import, model, arbitrary SQL, new dependency or migration is added. All data stays within the local application/database environment.

## Local authority and secret boundary

Two settings opt in: `BUTLER_WORK_SYNTHETIC_ADAPTER_ENABLED=true` and `BUTLER_WORK_SYNTHETIC_SECRET_DIRECTORY=/run/butler-work`. The optional Compose overlay configures these for API only and mounts a dedicated local named volume read-only there; migrate can prepare the file with a write mount. Normal Compose mounts no work-secret volume. The image contains an empty owned mode-0700 mount directory, never a credential.

The dependency constructs a lazy source without reading credentials. Current HTTPS/Host/Origin/session/user/CSRF/active workspace grant checks precede file access. Every authorized request opens `adapter.json` through an owned mode-0700 directory FD, rejects final directory/file symlinks and requires an owned, single-link mode-0600 regular file at most 4096 bytes. Duplicate/extra JSON fields, malformed/expired/oversized input, wrong environment/database/workspace/OID, placeholder/short secret and unapproved long validity fail closed. No host/DSN/role/SQL is accepted from file or request. Same-UID processes and the host/database operator remain trusted; this is not a hostile-host boundary.

The file binds schema version, development/test environment, database name/OID, workspace UUID, password validity and secret. Connection host/port/database come from existing server configuration; the managed login is derived from database OID/workspace UUID. Existing broker target/role/membership/family-denial/RLS checks apply. Errors are static and do not return file path, password, verifier, SQL or raw driver context. Secrets are hidden in model representations and never copied to database audit.

This is a **plaintext local secret file protected by OS/volume permissions**, not an encrypted vault. Do not copy it into Git, family memory, attachments, general archives or debug output. Docker/host administrators can read volumes. Review encryption/secret-manager and independent recovery before production or real credentials. Secret values also exist transiently in process memory; secure erasure is not claimed.

## Optional synthetic setup

No additional setup is needed for normal POC use. Run these only for explicit synthetic adapter validation after merging the PR and updating the checkout/image. Keep your existing `.env`, Compose project and data. If using another synthetic workspace, substitute only its slug.

```sh
# Keep using the existing project. This helper merely adds the reviewed overlay.
synthetic_compose() {
  docker compose --env-file .env -f infra/core/compose.yml -f infra/core/work-synthetic.override.yml "$@"
}

# If not already done: create/grant the synthetic workspace using WORK_ACCESS_FOUNDATION.md.
# Provision its NOLOGIN storage role while active (WORK_STORAGE_ISOLATION.md).
# Then disable before issuing or preparing a credential.
synthetic_compose run --rm migrate python -m app.work_manage --environment development disable --workspace synthetic-poc

# First issuance only, if prior implementation review's managed login has not already been bootstrapped.
# Generate/store a distinct password in your local password manager; enter it hidden twice.
synthetic_compose run --rm migrate python -m app.work_credentials --environment development bootstrap --workspace synthetic-poc

# Enter that current generated password at the hidden prompt. No -T or shell secret variable.
synthetic_compose run --rm migrate python -m app.work_adapter --environment development --workspace synthetic-poc --directory /run/butler-work

# Explicit opt-in process plus current workspace enable; neither grants a user permission.
synthetic_compose up -d --no-deps --build --wait api
synthetic_compose run --rm migrate python -m app.work_manage --environment development enable --workspace synthetic-poc
```

The existing authorized `POST /api/v1/work/workspaces/{uuid}/validation-read` is the sole read surface; it accepts only a strict `{ "limit": 1..25 }`, session cookie, exact Origin and current CSRF. No new UI read button or content capture is installed. Empty synthetic storage correctly returns an empty bounded page. Existing Work status continues to show content ingestion gates pending; adapter activation is not real-content readiness. Never place employer records in synthetic markers or family Memory.

Preparation requires a clean privileged local connection, disabled synthetic workspace, reviewed managed role and current server password validity no more than 25 hours away (issued by spec 016 for 24 hours). It verifies a fresh TCP password-authenticated login without reading markers. Require SCRAM/password authentication on the intended DB host; password validity does not constrain trust/certificate authentication. Metadata and minimal `admin.work_secret_prepared` audit commit before create-only atomic file publication. If file publication fails, prepared audit may remain: it is not a file-delivery receipt or distributed transaction. A failed audit/commit does not publish a file. Existing destination is never overwritten; no automatic retry. Inspect local state after ambiguous failures before repeating. The normal CLI prints no secret or file contents.

## Credential freshness and disable/rotate/revoke

Each read creates its own bounded engine, uses one short transaction, then disposes the pool before returning to the outer identity commit. There is no cross-request engine, password or authenticated-session cache. New requests reread the file and reauthenticate: file removal, expiry, an invalid secret, rotation or revocation yields sanitized unavailability instead of reusing an old connection. Credential expiry is checked before connection; it does not recall a read already in progress.

Workspace revocation remains the synchronization boundary: the merged exclusive registry mutation barrier waits for current readers through both commits. File deletion/config changes alone do not retroactively stop an in-flight authorized request. For rotation/revocation:

1. Disable workspace with the existing trusted command; wait for success. This serializes with in-flight authorized requests. Stop any separately configured consumers and drain connections. No independent consumer is installed here.
2. Use prior implementation review's rotate/revoke command while disabled. Existing observed managed sessions cause refusal; investigate them locally. Password changes/NOLOGIN do not themselves terminate sessions.
3. Remove only the prepared file through the trusted migration container. Do not remove the database volume.

```sh
synthetic_compose run --rm migrate python -m app.work_manage --environment development disable --workspace synthetic-poc
synthetic_compose run --rm migrate python -m app.work_credentials --environment development rotate --workspace synthetic-poc
# For terminal revocation, use revoke instead of rotate; no prompt is required.
synthetic_compose run --rm migrate python -c 'from pathlib import Path; Path("/run/butler-work/adapter.json").unlink(missing_ok=True)'
```

4. Rotation only: prepare a new file with the new password, then explicitly re-enable the workspace. Revocation leaves a disabled tombstone; no silent reissue. To return to ordinary disabled POC mode, keep workspace disabled and recreate API with the standard Compose file (without the overlay). The named secret volume may remain; deliberate file removal is needed to remove its current secret.

The application barrier governs supported registry/API operations, not a malicious superuser, arbitrary direct login or racing trusted manual enable. Per-request disposal favors simple credential freshness over connection reuse; later pooling requires explicit generation/session fencing. Queue/connect/SQL budgets are bounded, but an end-to-end hard deadline under every network partition is not claimed.

## Verification and recovery

Unit tests exercise protected-file modes/ownership/symlinks/hardlinks/FIFO/size/schema/duplicates/binding/expiry, no unauthorized file reads, non-TTY/echo fallback refusal, create-only publication and per-lease disposal. Actual PostgreSQL tests cover file→managed login→scoped broker audit, fresh sessions, wrong credential/OID, file removal/expiry, disable/rotate/revoke and reprepare, and failed prepared audit. Existing both-commit revocation, migration and work/family restore tests remain. CI runs normal disabled browser acceptance first, then the explicit non-root overlay with a synthetic-only secret volume and verified TLS read/removal probes. Cleanup deletes disposable CI volumes only. This is hosted evidence, not new M2 acceptance.

No credential restore is added. Ordinary DB dumps omit cluster roles; the dedicated secret volume can contain plaintext and must not be blindly included in general archives. After recovery keep workspace and adapter disabled; review new database OID/roles, session revocation, independently stored password-manager material, reissue/rotation and prepared files before any enable. Issue #5 (historical private reference omitted) retains independent host/key/secret recovery acceptance.

Next: work domain content lifecycle/retention/correction/forget/export/key contracts, isolated context/jobs and recovery before a synthetic debrief/action pilot. Real employer data, external services and production remain separate approvals.
