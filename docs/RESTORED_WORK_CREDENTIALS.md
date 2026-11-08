# Review Work credentials on an isolated restored cluster

Use this privileged development/test procedure after [Work restore quarantine](WORK_RESTORE_QUARANTINE.md) has disabled the selected synthetic workspace and removed **all** its grants. It inventories one workspace's current and copied cluster role namespaces and can revoke an explicitly selected set of logins. It does not recover secrets or authorize activation. No content or credential material leaves the local target.

Keep the restored server isolated from application traffic. Stop consumers, dispose pools and drain connections across **all databases**, and stop other trusted role administration during review/apply. NOLOGIN and password changes do not kill an existing session or fence authentication already in progress. Do not use this procedure as emergency compromise containment. A fresh inspection after commit is required, and still describes only the observed instant.

## Inventory, review, apply, inspect

Use the existing privileged maintenance environment pointed explicitly at the isolated restored database. Never point the normal API at the restore. The examples use placeholders for public UUIDs/OIDs; do not supply role names, passwords or verifiers.

```sh
python -m app.restore_credentials --environment development \
  --restored-database RESTORED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID
```

This first read-only preview lists at most 25 namespaces, including role presence, public role OIDs, login status/expiry, whether a database currently has that namespace OID, and observed login connection counts across the cluster. Overflow or malformed reserved names fail; no partial inventory is approved. `selected_profiles_verified=false` when nothing is selected. Inventory is public catalog metadata, not proof of credential safety or provenance. `pg_authid`, passwords and verifiers are never read by the tool.

The names follow `butler_work_<database OID>_<workspace UUID hex>` and `butler_wlogin_<database OID>_<workspace UUID hex>`. An absent source database makes an OID an **orphan namespace**, not an authenticated source identity. OIDs may have been reused. Review origins independently. Other workspaces, arbitrary role names and OS/password-manager secrets are outside the inventory.

Select 1–10 sorted unique OIDs explicitly. Repeat the flag for multiple namespaces. A selected current namespace or orphan must contain both storage and login roles matching the existing credential profile: no elevated/ownership/family/DDL privileges, unexpected settings/direct login grants or incoming/outgoing memberships. This is not an exhaustive cross-database ownership or storage-ACL certificate. A selected noncurrent OID that still belongs to a database in this cluster is refused, even if the source is stopped. The tool never changes that source's credentials. Unknown profiles require separate manual investigation, not automatic repair.

```sh
python -m app.restore_credentials --environment development \
  --restored-database RESTORED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID --namespace-oid SELECTED_OID
```

Review the **entire current** result, including unselected inventory and connection counts. Use its exact `issued_at` and `reviewed_hash` within five minutes. Include the same sorted OID flags:

```sh
python -m app.restore_credentials --environment development \
  --restored-database RESTORED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID --namespace-oid SELECTED_OID \
  --issued-at EXACT_SERVER_ISSUED_AT --reviewed-hash EXACT_REVIEWED_HASH \
  --decision revoke_restored_credentials
```

Apply refuses observed selected-login sessions anywhere in the cluster. Changed inventory, role identity/status, selection, target, workspace or review time requires a fresh preview. All already-disabled selections produce no completion receipt. Replay cannot advance or reuse a completed plan. No automatic retry after an uncertain commit: inspect local role metadata and the receipt before deciding what to do next.

For the selected pairs only, apply sets `NOLOGIN PASSWORD NULL` and removes the expected SET membership. It does not drop roles, terminate sessions, reset platform human passwords, issue new credentials, delete adapter files or alter unselected credentials/content. Transactional role DDL and `admin.restored_work_credentials_revoked` metadata audit commit or roll back together. Public namespace OIDs, target/workspace/operator references, plan hash and explicit unknowns appear in the receipt; no verifier or secret does.

Repeat the inventory command after commit, inspect selected `can_login=false` and observed connections, and keep the workspace disabled/no-grant. Inventory cannot prove that an already-disabled role's password is null because the tool intentionally does not read verifiers; password clearing is an effect of a successful apply receipt. If a connection remains or appears, keep isolation and investigate/drain it manually. No session-termination helper is installed.

## Authority and limits

Explicit configured/actual target name and OID, matching development/test environment, a clean superuser READ COMMITTED transaction and an active technical-admin audit reference are required. Test databases must start with `butler_test`. The existing registry try-lock precedes fail-fast business-table locks and operator protection. These barriers coordinate registry operations in this database; they are not a cluster-wide lock against arbitrary administrators or in-flight logins. Trusted host/cluster administrators and network isolation remain prerequisites.

Fresh credentials for a separately reviewed target must follow the [credential lifecycle](WORK_CREDENTIAL_LIFECYCLE.md) and [protected-file adapter recovery](WORK_SYNTHETIC_ADAPTER.md). Revoked login tombstones cannot be reactivated by rotate/bootstrap. Do not copy old verifiers, silently replace tombstones or reuse source secrets. Independent password-manager/key recovery, other workspace and cluster roles, source/derived/unmanaged copies, latest forgetting and whole-host/off-site acceptance remain open. Every plan/receipt retains `activation_authorized=false` and `recovery_complete=false`.

The final existing PostgreSQL restore job and maintenance-container job both run the real CLI against synthetic current/orphan pairs, verify replay refusal, actual TCP denial, disabled workspace and audit receipt. They do not demonstrate an independently recovered host or owner secret store.
