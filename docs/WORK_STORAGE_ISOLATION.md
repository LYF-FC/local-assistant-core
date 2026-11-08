# Work storage isolation — synthetic development/test boundary

Spec 013, merged through #35, continues #34's explicit workspace access registry. It adds a private PostgreSQL schema and independently scoped validation roles. **No work content API, application connection, login credential or debrief feature is enabled.** The Work Companion screen remains ingestion-disabled with its existing five content gates. This is one storage building block, not full spec 005 acceptance.

## Implemented contract

| Object | Contract |
|---|---|
| `work` schema | Private; PUBLIC has no schema/table/function grants. Family `butler_runtime` has no work access or role membership. |
| `work.validation_records` | Insert-only synthetic marker, 11–256 bytes, prefixed `synthetic:`; server-set timestamp. Composite `(workspace_id,id)` key avoids cross-workspace UUID uniqueness probes. Not a debrief/task/memory domain table. |
| `work.validation_audit` | Work-scoped, content-free database-role mutation audit. Insert trigger writes it in the same transaction; no marker copy. No direct insert/update/delete/truncate for storage roles. |
| `work.active_workspace` | Security-barrier view returning only the active workspace UUID matching the effective database role and current database OID; underlying identity table access uses the trusted migration owner. No name, family identity or membership catalogue is exposed. |
| Storage role | `butler_work_<database_oid>_<workspace_uuid_hex>`; NOLOGIN/NOINHERIT, no ownership, memberships, superuser, DB/role creation, replication or RLS bypass. Explicit SELECT on the view/validation/audit and column-limited INSERT on validation records only. |
| Row policies | ENABLE + FORCE RLS on both tables; role-bound active workspace filter and write check. Caller-supplied workspace settings cannot select another workspace. Current workspace disablement applies on subsequent statements. |
| Recovery operator | Explicit migration-owner policy; privileged host/database operators can recover all data and change DDL. Shared infrastructure does not provide physical/admin isolation. |

No automatic workspace, user grant or storage role is seeded. Existing users, scopes, configuration and volumes remain intact. No model, external data transfer, scheduler, connector or new dependency is added. New future tables receive no implicit grants; each needs its own reviewed policies and audit lifecycle.

## Trusted provisioning

After migration 0007 on a checked candidate/main, the local operator may explicitly prepare a **previously created active synthetic workspace** using the existing migration container. Keep the same POC exports/project:

```bash
export COMPOSE_PROJECT_NAME=butler-poc
export BUTLER_LOCAL_CA_FILE="$HOME/Butler/exports/butler-poc-root.crt"
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_storage --environment development --workspace synthetic-poc
```

This is optional validation preparation, not needed to keep the current POC working. It creates a NOLOGIN role only; it does not let the API, `poc-owner`, `poc-viewer` or a human workspace member connect/assume it. Membership remains administered through `app.work_manage` as described in [WORK_ACCESS_FOUNDATION](WORK_ACCESS_FOUNDATION.md). Identity administration audit contains only the workspace UUID and event, not marker content or credentials.

Provisioning rejects unsafe existing login/elevated/member/owner roles. It clears explicit database/table/column/function/schema grants in the known public/work namespaces before installing the exact allowlist. Platform setup must already have removed PUBLIC database CREATE/TEMP and public-schema CREATE. It generates identifiers from typed UUID/OID values, not a caller-supplied role name. No secret input/output is introduced.

## Testing and enforcement limits

PostgreSQL tests create temporary **test-only** login harnesses with permission to assume exactly one workspace storage role. They actually authenticate as those restricted logins; using a superuser session with SET ROLE would not prove SET ROLE escalation denial. No harness login is installed by development Compose/CLI.

Acceptance checks cover family↔work schema/table/role denial; workspace A↔B reads/writes/role denial; copied UUID independence; forged workspace settings and row_security=off; active-workspace changes; database/server timestamps; bounded marker validation; no default grants to future tables; insert/audit atomic rollback; column privilege repair; unsafe existing role rejection; and owner/runtime append-only guard checks. Original Memory/Discovery/Context/HTTPS/browser tests remain in CI.

The private schema is migration-managed SQL, intentionally outside the public ORM metadata. `alembic check` continues checking the public model; targeted schema/catalog/round-trip tests verify the private tables, forced RLS and triggers.

Raw validation-role SQL is a trusted test/operator surface, not an application read API. It has database-role mutation attribution; it does **not** implement current human membership enforcement or audited work-content reads. Before any content service/login is enabled, a separately reviewed connection/credential broker must bind current user/session/workspace grants to every transaction, serialize/recheck revocation through response release, produce work-scoped read/deny audit and avoid shared caches/connections. A human work grant is never a database-role grant.

## Logical restore and portability

The disposable restore procedure reapplies the reviewed platform runtime/database grants before provisioning a work role: a newly created destination database otherwise retains default PUBLIC TEMP permission. Work provisioning fails closed on that unsafe baseline. The existing disposable `butler_test` → `butler_test_restore` check now preserves synthetic work records/audit, forced row policies and ACL. A role tied to the source database OID cannot read copied rows in the restored database even when the dump copied its object ACL. Trusted explicit reprovision creates a distinct NOLOGIN role for the restored database/workspace; that role sees only its restored workspace. Existing family audit/outbox/forgotten-memory checks remain.

This is same-cluster logical recovery, not independent-host, encrypted backup, separately recovered keys, retention expiry, session revocation or full work-content recovery. PostgreSQL database OIDs are deployment-local; workspace UUIDs remain stable. A fresh-cluster restore needs a separately tested role/ACL recreation procedure (database dumps do not create cluster roles), a trusted registry manifest and quarantined restoration before connections are enabled. Those production gates remain issue #5.

Downgrade drops only this migration's schema objects, never cluster-global roles automatically. NOLOGIN roles may remain after a disposable downgrade; a trusted operator must review cluster role cleanup separately. Future content/corrections/forgetting/exports/keys/retention models are not silently defined by append-only synthetic validation tables.

## Continue the M2 POC after merge

Use the [HTTPS main update and rebuild procedure](WORK_ACCESS_FOUNDATION.md#update-an-existing-m2-checkout-over-https), preserving `.env`, users and volumes. If previewing before merge, stay on the checked candidate until main includes migration 0007; do not rebuild an older main against a newer database. No new UI flow or role provisioning is necessary for the existing synthetic POC.

Technical references: [PostgreSQL 17 row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html), [view security](https://www.postgresql.org/docs/17/sql-createview.html), [SET ROLE session permissions](https://www.postgresql.org/docs/17/sql-set-role.html).

## Current authority guard

Spec 014 candidate serializes work registry reads with current user/session/grants and commit. It does not add storage credentials or application connections. See [WORK_TRANSACTION_AUTHORITY](WORK_TRANSACTION_AUTHORITY.md). The NOLOGIN validation boundary and remaining content gates above remain unchanged.
