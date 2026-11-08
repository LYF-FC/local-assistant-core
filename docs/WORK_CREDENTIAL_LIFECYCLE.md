# Synthetic work credentials — trusted local lifecycle only

Spec 016 adds a privileged local development/test utility for bootstrap, rotation and revocation of one synthetic database/workspace login. It does **not** install a work adapter, secret file, environment variable, HTTP endpoint or credential in the normal API. The default `get_work_engines()` returns None; optional loading/activation is now the separate [spec 017 runbook](WORK_SYNTHETIC_ADAPTER.md). Nothing is automatically run during install, migrations, CI deployment or restart.

## Preconditions and authority

Use the existing privileged migration container, never the API or family runtime role. Require a matching explicit development/test environment, a `synthetic-` workspace, its previously provisioned NOLOGIN storage role, a **disabled** workspace and stopped consumers. Tests require disposable `butler_test*` databases. The utility checks a clean superuser READ COMMITTED connection, acquires the existing exclusive registry advisory barrier before the workspace row lock and applies two-second lock/five-second SQL waits. These are database budgets, not a universal network deadline.

First provision the storage role with the existing [storage procedure](WORK_STORAGE_ISOLATION.md) while the workspace is active, then disable it with `app.work_manage`. Storage provisioning, identity user grants and credential issuance remain distinct operations. The helper neither provisions nor repairs platform PUBLIC privileges.

The login name is `butler_wlogin_<database OID>_<workspace UUID hex>`. It is derived locally, never accepted as caller SQL/role input. Bootstrap refuses any existing reserved login; rotate requires the existing reviewed LOGIN principal; revoke accepts that principal or its clean disabled tombstone. Role drift (ownership, inheritance, elevated flags, extra memberships, family/table/column grants, role/database settings) fails closed without repair. A managed login receives only one non-admin, non-inheriting membership with permission to SET the matching storage role. It has no direct object grants.

## Local commands

These commands are optional; ordinary POC updates need none of them. Run in your existing checkout with the existing `.env` and Compose project. Do not create a new project or volume.

```sh
# Stop any separately configured work consumers and drain/dispose their pools first.
# No work consumer is installed by the normal POC.
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_manage --environment development disable --workspace synthetic-poc

# Use a local password manager to generate/store a distinct 32–256 character
# printable ASCII secret (no spaces). Enter it twice at the hidden local prompt.
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_credentials --environment development bootstrap --workspace synthetic-poc

# Later rotation: stop/drain consumers and keep workspace disabled; enter a new secret.
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_credentials --environment development rotate --workspace synthetic-poc

# Revoke: no password prompt; repeat is safe. Workspace stays disabled.
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_credentials --environment development revoke --workspace synthetic-poc
```

Do not add `-T` to the secret-entry commands: they require a local TTY and refuse visible-input fallback. Passwords are never accepted in argv/environment/stdin automation, printed, returned, persisted as a client file or written into audit. Empty/short/oversized/non-ASCII/whitespace/placeholder/migration-equal inputs are rejected without echo. Password policy cannot prove randomness or detect reuse of a previous secret; generate distinct credentials in the password manager. Prompt values exist transiently in Python memory; secure erasure is not claimed.

libpq generates a SCRAM-SHA-256 verifier client-side; raw passwords never enter the ALTER ROLE statement. The verifier is still sensitive. Ordinary statement/duration/error statement logging is suppressed within that privileged transaction; host tracing/audit extensions and database superusers remain trusted. Review those systems before any real credentials, and never capture secret-entry sessions. See [Psycopg libpq API](https://www.psycopg.org/psycopg3/docs/api/pq.html) and [PostgreSQL ALTER ROLE](https://www.postgresql.org/docs/17/sql-alterrole.html).

Bootstrap/rotate sets password validity to 24 hours for new password-authenticated connections. Expiry does not revoke an already-open session and does not affect non-password authentication methods. Configure password/SCRAM authentication on the intended host; CI tests actual TCP password authentication, including old-password refusal.

## Transactions and revocation limits

Role DDL and minimal identity audit (`admin.work_credential_bootstrap/rotate/revoke`, workspace UUID, fixed operator identity, no role/secret/verifier metadata) commit together or roll back together. Audit insertion or commit failure means no success confirmation; inspect local state before retrying an ambiguous network failure. No automatic retry. CLI errors omit raw driver/SQL details; audit failure cannot promise a durable denial record in an unavailable store.

Revoke removes the expected SET membership, sets NOLOGIN and clears the stored password. It leaves a tombstone rather than silently dropping/reusing a cluster-global identity. Bootstrap will not overwrite it; rotate will not reactivate it. Reissue needs a separately reviewed operation.

**Password rotation and NOLOGIN do not terminate established sessions.** The utility rejects an observed existing managed-login session across databases. The disabled-workspace RLS boundary continues to return no rows even to an already-assumed storage role. This observation is not a fence against an in-flight login or a trusted operator racing manual enable. Stop all consumers and drain connections first; keep the workspace disabled after every operation. There is no session-killing feature or automatic re-enable. Future activation must independently implement/review pool disposal, concurrent credential changes, session fencing, secure secret loading and credential expiry handling. Do not use these commands as an emergency compromise containment guarantee.

## Recovery and next gate

No new schema migration or dependency. Ordinary PostgreSQL database dumps do not include cluster-global roles/passwords; these credentials are intentionally not recreated by restore tests or stored with family memory/backups. A restored database has a different OID/name mapping; never blindly copy source login verifiers/memberships. Retain secrets only in the operator's local password manager; secure backup/recovery of that manager remains separate. Existing private schema/RLS/audit logical restore coverage remains unchanged; this is not whole-host or secret-recovery acceptance.

Spec 017 is the separately reviewed protected-file synthetic activation candidate, with per-request disposal and explicit workspace fencing. Next is work-content lifecycle/retention/forget/export/keys and independent secret/host recovery before debriefs or employer records. No real work data, model, Discovery collector, financial execution or external service is enabled here.


For isolated restores, [inventory and explicitly revoke current/orphan namespaces](RESTORED_WORK_CREDENTIALS.md) before considering fresh target provisioning. That procedure does not issue/rotate secrets, modify an existing source database namespace or override tombstones.
