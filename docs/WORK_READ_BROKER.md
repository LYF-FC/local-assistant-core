# Scoped synthetic work read broker — default disabled

Spec 015 connects the merged #36 identity transaction guard to the private synthetic work validation schema through an explicitly trusted per-workspace Engine mapping. **The default provider returns None.** Merged #38 supplies optional local managed-login lifecycle commands; spec 017 adds a separately opted-in protected-file source and per-request engine leases (see [activation runbook](WORK_SYNTHETIC_ADAPTER.md)). Normal install creates no login/mapping/content source/UI read control. This is a tested broker/adapter boundary before credential activation and domain content design, not a ready professional-data assistant.

## Request and data boundary

`POST /api/v1/work/workspaces/{uuid}/validation-read` accepts only `{limit: 1..25}` (default 10), with strict integer/extra-field validation. HTTPS/exact Host/Origin, session, CSRF and current active user/workspace grant checks precede any work connection. A missing or disabled adapter yields sanitized 503; an unassigned/unknown workspace yields the same 404. No client user ID, role, DSN, SQL, action or prompt is accepted.

The normal UI remains unchanged and ingestion-disabled. Real TLS/browser CI exercises default-disabled 503 and CSRF denial, not a hidden active data integration. No model, connector, scheduler, new dependency or external data transfer is added. Data stays within the current local PostgreSQL/application boundary.

## Trusted engine adapter

WorkspaceEngines copies a trusted UUID→Engine map into an immutable mapping. The factory takes an explicit trusted URL only, with no shared administrator fallback. The optional file source constructs that URL from server target settings and derived managed login, never a file DSN. It uses two pooled connections per workspace, no overflow, two-second queue wait and three-second initial connection timeout. The broker also enforces a bounded QueuePool and same PostgreSQL+psycopg driver, host, port and database as the identity connection; unexpected URL options/targets are rejected before checkout.

Every work transaction verifies actual database OID, clean session/effective identity and READ COMMITTED. The login must be non-elevated, NOINHERIT, non-owner, with no family table/column/DDL access and exactly one non-admin, non-inheriting membership allowing SET to the matching NOLOGIN workspace role. That role must be non-elevated/non-owner with no inherited memberships. SET LOCAL ROLE then verifies the effective role and exact active workspace. Mislabeled, privileged, cross-workspace, stale-role or stale-isolation adapters fail closed. A connection with unexpected role/profile is discarded; the current request is not retried.

These checks defend configuration mistakes; the injected provider and host/database administrator remain trusted code/operators. A malicious host or arbitrary engine creator is not a physical/network isolation boundary. Production credential creation/storage/rotation and network-fault/request budgets are still separately reviewed gates; SQL/queue/connect budgets here are not a universal end-to-end network deadline.

## Bounded read and role cleanup

The only data query is a fixed, parameterized single-workspace SELECT ordered by UUID, with explicit workspace predicate plus existing forced RLS. It reads at most limit+1 synthetic markers and returns at most limit, with has_more. No fallback across owners/workspaces, arbitrary SQL, domain write, model or tool execution. Clock authority is checked before and after the data query and after work commit; expiry returns no rows.

The outer identity transaction keeps registry/user/session locks through work read audit and the final identity audit/commit. Separate-connection tests hold both commit stages and observe that raw/helper revocation cannot commit prematurely. Authority is freshly derived per request and is never placed in the pool. SET LOCAL role/timeouts end with the transaction; pooled session-role residue is rejected/discarded, not trusted as actor authority.

## Honest work-scoped audit semantics

Migration 0009 creates `work.read_attempts`: workspace, actor/session UUID, event, bounded source UUID list/count, reason and server time. There are no marker/text/title/credential copies. IDs/count are bounded to 25. Forced workspace RLS and append-only mutation/truncate guards apply, with an explicit trusted recovery-owner policy. The role provisioner grants SELECT and only the necessary INSERT columns; ID/time cannot be caller-set. No user/session FK is used to expose family identity through service-role integrity probes: actor/session provenance comes from the locked server identity, not from a browser body.

Work read audit is a **prepared** or **denied** attempt, never a delivery receipt:

- Expiry before/after query records denied if that scoped audit can commit; no rows reach HTTP.
- Work audit/commit failure returns no rows and does not automatically retry the read.
- After work prepared audit commits, clock is checked again and the identity audit must commit before payload release. Post-work-commit expiry leaves the earlier prepared event but returns no rows.
- If identity audit/commit then fails, prepared work audit may remain while HTTP returns sanitized unavailability with no items. This is truthful evidence of preparation, not claimed delivery or distributed atomicity.

Missing-grant/CSRF denial is audited in identity metadata without opening the requested workspace connection. Infrastructure failure cannot promise persistence to an unavailable audit store; it always fails closed. Ordinary future work-content audit review/retention remains a separate permission/lifecycle design, not a public audit viewer supplied here.

## Verification and recovery

Actual restricted-login PG tests cover scoped bounded reads and audit/source references, rejected unassigned checkout, peer/family/admin/wrong-target/stale-isolation adapters, broad column grants, unbounded pools, read-audit/work-commit/identity-commit failure, expiry before/after query, grant locking through both commits, pool role reset/discard and per-workspace audit isolation. Existing work/family SQL/RLS/registry authority tests remain.

Logical restore includes read-attempt provenance/count, copied-source-role denial, destination platform grant hardening and distinct NOLOGIN-role reprovision, forced RLS and immutable read audit. This does not certify independently recovered credentials/keys, restored-session revocation, domain deletion/retention or full-host recovery (#5).

After merge/green main, the existing [HTTPS main update/rebuild](WORK_ACCESS_FOUNDATION.md#update-an-existing-m2-checkout-over-https) applies migration 0009 while preserving users/.env/volumes. No new credentials or role command is required to keep the current POC working. Optional storage-role reprovision adds private read-audit grants but still creates no login or active provider. Stay on a migration-bearing preview until main contains the same migration.

Credential lifecycle is now spec 016 candidate (see [local runbook](WORK_CREDENTIAL_LIFECYCLE.md)); no normal provider is installed. Next: review secure loading, session/pool fencing and explicit synthetic adapter activation, then content lifecycle/retention/forget/export/keys and isolated context/jobs/recovery before debrief capture or any employer source. Do not paste employer content into generic family Memory or synthetic validation markers.

Technical references: [SQLAlchemy Engine/Connection transactions](https://docs.sqlalchemy.org/en/20/core/connections.html), [PostgreSQL SET ROLE](https://www.postgresql.org/docs/17/sql-set-role.html), [row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
