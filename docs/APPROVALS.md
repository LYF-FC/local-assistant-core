# Approval and audit foundation — development/test

Development foundation is in main through merged #26; issue #3 is closed for this bounded slice. Production deployment and external actions remain disabled. Only action type validation.noop is supported; consumption records a one-time claim without executing a tool. Durable external execution/outbox belongs to a later feature.

## Bound approval

The scope-authorized requester creates a pending record. The server binds requester, scope, action, payload, policy version and UTC expiry with a SHA-256 digest of Butler v1 compact/sorted UTF-8 JSON. Negative numeric zero is normalized; nonfinite values, excessive nesting/collections and oversized payloads are rejected. This format is versioned and does not claim RFC 8785 compliance.

The reviewer fetches the exact scoped record, then repeats its payload_hash and policy_version when approving/rejecting. Expiry is 60..3600 seconds. Pending may become approved, rejected, cancelled or expired. Approved may become consumed, cancelled or expired. Terminal decisions cannot be replayed. Payload/context/expiry are sealed by PostgreSQL guards. Unbound legacy rows stay unchanged but cannot authorize a decision or consumption.

Any current member of the record’s scope may review/approve/reject this no-op mechanism; self-approval is permitted. Only the requester may cancel/consume. At consumption, the original approver must still be active and hold the same scope. Scope removal/disablement and policy changes invalidate stale authority. Distinct sessions still compete on a locked approval row, so at most one transition wins.

## API

All routes require an active HTTPS session. Unsafe methods also require exact Origin and X-CSRF-Token. Technical administration is not a private-content override.

- POST /api/v1/approvals: scope, action_type=validation.noop, payload object, optional expires_in (default 900). Returns pending record/hash/policy.
- GET /api/v1/approvals/{id}: SQL scope-filtered retrieval. Missing/cross-scope IDs return the same 404. Deterministic expiry may be recorded here.
- POST /api/v1/approvals/{id}/decide: decision=approve|reject plus payload_hash/policy_version.
- POST /api/v1/approvals/{id}/cancel: payload_hash/policy_version, requester only.
- POST /api/v1/approvals/{id}/consume: same binding, requester only, approved and unexpired no-op only.

Mismatch/stale/invalid transition returns 409; missing identity 401; scope/CSRF/owner denial 403; malformed input 422. Database or audit/commit failure releases no success response or state change. Audit records state transitions and binding metadata, not duplicate raw payloads or tokens.

## Database boundary

Migration 0003 adds binding fields, approval state guards, and audit guards rejecting normal UPDATE/DELETE/TRUNCATE. The API connects as butler_runtime, not a table owner/superuser. It can append audit, perform identity/session/rate operations and update approval states; it cannot administer users/scopes, read audit wholesale, disable guards or run DDL.

The runtime has column-only UPDATE on users.updated_at because PostgreSQL requires an UPDATE privilege for the login row lock. Account identifiers, active status and scope grants remain read-only.

A one-shot role_setup uses privileged migration credentials after migrations, sets explicit grants and a separate generated runtime password, then exits. It refuses unreviewed membership/ownership and never prints secrets. Public schema/database create/temp privileges are restricted in the dedicated development DB. The API waits for setup success and development startup refuses migration credentials.

Host/database administrators can alter/drop guards: this is normal-runtime protection, not owner-proof immutable storage or cryptographic nonrepudiation. A compromised application with write credentials may append forged new events; independent archival/tamper evidence and host security remain production work. Future domain isolation, audit inspection UI, retention and real executors require separate acceptance.

## Development and recovery

.env now requires distinct BUTLER_POSTGRES_PASSWORD (migration/admin) and BUTLER_RUNTIME_PASSWORD (API). first-run.sh generates a runtime secret for a new or existing development .env; it never publishes PostgreSQL. Do not reuse administrator credentials for the API.

Trusted account administration must run through the privileged migration container after applying migrations:

```sh
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.manage --environment development create-user --slug synthetic-user --display-name 'Synthetic user' --scope household_shared
```

The runtime API container deliberately lacks these administrative DB grants. Use an interactive trusted terminal and synthetic accounts; no real accounts are created automatically. Existing HTTP shell remains status-only; target-host TLS/proxy/UI acceptance and production startup remain gated.

Test fixtures roll back transactions rather than delete protected audit rows. Real committed race fixtures exist only in a disposable CI database. The destructive migration test removes guards through their explicit privileged downgrade before dropping test tables; this is not a production rollback procedure.

Backups include protected audit/approval records and guards. Restore through the trusted owner path, verify data and guard rejection, provision reviewed runtime grants, revoke restored sessions and reconcile pending/consumed work before enabling actions. Runtime credentials cannot perform a restore or disable audit protection.
