# Reviewed restored Work credential quarantine

## Outcome
A technical operator can inventory bounded current/copied cluster Work role namespaces for one disabled synthetic workspace, select explicit database OIDs, review an exact metadata-only plan and atomically disable selected logins, clear passwords and remove their SET memberships with an audit receipt. No data leaves the local target. No secrets are accepted or read. No migration/API/runtime grants.

## Requirements
- Explicit matching development/test target, actual database name/OID, clean superuser READ COMMITTED transaction and active technical-admin reference.
- Disabled synthetic workspace with zero grants, registry barrier before business locks; callers stop consumers and isolate/drain the recovery server.
- Inventory at most 25 namespaces; reject overflow, malformed reserved names and unknown selected profiles. Initial inventory needs no selection and grants no apply authority. Select 1–10 sorted unique OIDs for a reviewed apply; no automatic namespace selection.
- Reject a selected noncurrent namespace if its source database still exists in this cluster. Never modify another live database's credentials.
- Validate exact role/login profiles, direct grants and incoming/outgoing memberships; return only public catalog metadata, never pg_authid/verifiers.
- Hash binds target/operator/workspace, catalog role OIDs/profiles, selection, inventory and five-minute server timestamp. Fresh preview required on changes/replay. Refuse observed sessions across all databases.
- Apply only NOLOGIN/PASSWORD NULL and removal of expected membership. No termination, role drops, grants, secret reissue, activation or completeness certificate. Role DDL and audit roll back together.
- NOLOGIN is not a fence against in-flight authentication and existing sessions. Always retain explicit unknowns and require a fresh post-commit inspection; whole-cluster role/other-database ownership and actual host acceptance remain unverified.

## Acceptance
Real PostgreSQL tests cover current/orphan namespaces, preserved unrelated login, live source refusal, role drift, stale/replayed/tampered plan, active connections, rollback, busy registry, authorization and actual TCP credential denial. Exercise the actual maintenance CLI in a container. Existing full four-job CI remains mandatory.
