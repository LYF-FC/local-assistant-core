# Reviewed synthetic Work restore quarantine

Spec 031 provides a manual local recovery prerequisite. Before exposing a restored synthetic database to applications/workers, preview a chosen workspace's restored access and sessions, then explicitly apply the exact reviewed quarantine. It disables that workspace, removes all its Work grants and revokes every unrevoked platform session of its current grantees, atomically with a completion receipt. Nothing leaves the private environment.

## Operator procedure

Keep applications/workers stopped during restore and review. Use the restored configuration and short-lived trusted migration connection, preserving the intended users, CA, secrets and volumes. Do not connect the normal application merely to inspect restored sessions. Development/test synthetic workspaces only; test databases must be disposable `butler_test*` names. No schema migration, credential/grant/dependency, API route, UI or automatic service is added.

Select an active `technical_admin` user as the operator audit reference. This selected UUID is neither HTTP human-session proof nor permission to reactivate Work. The command requires the clean READ COMMITTED owner of registry/users/sessions/audit. Ordinary runtime/scoped/assumed roles fail closed. Explicitly name the restored database; the argument must match both configuration and the actual database. Its name/OID appear in the reviewed plan. This acknowledgement cannot prove restore origin, backup freshness or completeness.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_restore --environment development \
  --restored-database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID
```

Use the actual restored environment/database and synthetic UUIDs in place of placeholders. Review the metadata JSON locally: database name/OID, workspace/operator, current enabled state, grantee UUIDs, affected session UUIDs/user/expiry/last-seen, issue time and `reviewed_hash`. No note, label, token, CSRF secret, credential or content-derived hash is read or output. The digest covers only metadata.

**Affected users are signed out across scopes and workspaces.** Sessions are platform-wide, so one restored Work grant identifies all that user's unrevoked sessions, including family sessions and expired-but-unrevoked rows. Grants to other workspaces and unrelated users' sessions stay unchanged. Confirm these effects in the preview before applying.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_restore --environment development \
  --restored-database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID \
  --issued-at PREVIEW_ISSUED_AT --reviewed-hash PREVIEW_HASH \
  --decision quarantine_restored_workspace
```

Copy the exact issue time/hash from that preview. Review lasts at most five minutes, including the end of apply. Every grant and affected session must still match; changes reject the whole operation. At most 25 grantees, 100 sessions and 32 KiB metadata are supported. Oversized operations fail without truncation. Do not delete grants first to bypass a cap: that loses the membership-to-session mapping. Use a separately reviewed recovery procedure for larger targets.

The exclusive Work registry barrier precedes workspace, ordered user and session locks; existing authorized Work transactions must finish or roll back first. User locks serialize with sign-in before sessions are selected. Lock/statement timeouts fail closed. Any audit, guard or commit failure rolls back disable, grant removal and session revocation together. Output follows commit. `admin.work_restore_quarantined` stores selected operator, metadata plan hash, removed user/session IDs and receipt UUID; it is evidence, not an enable token.

After an uncertain commit, inspect current metadata and receipt using the trusted connection. Re-preview deliberately before retry. Reusing the old plan fails; an already quarantined workspace cannot create a no-op success receipt. A receipt always says `workspace_enabled=false` and `recovery_complete=false`. No command re-enables a workspace or regrants access.

## What remains separate

This tool leaves private content and existing forgetting/retention evidence untouched. It does not reconcile newer forgetting decisions into an older backup, erase review/request payloads, rotate passwords/keys, invalidate all other restored workspaces or sanitize old jobs/approvals. Passwords remain usable for a fresh sign-in; that does not restore the removed grant to this disabled workspace. Users who had no grant to this workspace at preview are outside its session set.

This is a manual procedure, not an enforced startup quarantine flag, immutable recovery certificate or prohibition on later trusted administrator changes. Keep restored Work offline until applicable newer-suppression/source/key/derived-copy/export/credential/job/full-host gates are separately verified. Review every restored workspace separately. Explicit regrant/enable is a later owner-reviewed acceptance step, never a side effect of cleanup or this receipt. Real employer content and complete issue #5/spec 005 remain gated.

## Verification

Real PostgreSQL tests cover target/operator/role/isolation/time/bounds, multiple sessions, shared-user sign-out, unrelated preservation, stale/replay denial, serialization and audit rollback. The migration-container smoke executes actual CLI preview/apply/replay. The logical restore drill copies a synthetic active session, verifies it initially resolves, quarantines the restored workspace after scoped-role inspection, then verifies session resolution is denied, all grants are gone, the workspace is disabled, private notes/redactions are identical and the receipt is retained. Existing full TLS/browser/security/restore gates remain required. No actual M2 or independent clean-host recovery is claimed.

Spec 032 adds reviewed reconciliation of supplied terminal decisions into older quarantined synthetic snapshots using a protected independent metadata file. It does not prove latest complete coverage or full-host recovery. See [WORK_BACKUP_SUPPRESSION](WORK_BACKUP_SUPPRESSION.md).

After quarantine, separately review applicable known-checkpoint forgetting reconciliation and [restored pending-input cleanup](WORK_RESTORE_REQUESTS.md). Quarantine itself does not discard queued Work requests or cached review hashes. None of these steps enables Work or certifies full recovery.

Work-grantee sign-out does not cover every platform user. Before exposing any restored service, complete the separate [global restored-session quarantine](RESTORED_SESSION_QUARANTINE.md) batches, including users without Work grants. Neither tool automatically restarts services or certifies full recovery.
