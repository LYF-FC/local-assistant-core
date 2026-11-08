# Spec 013 — Quarantined work storage isolation

Bounded continuation of spec 005 after merged #34. No work application content API or credentials are enabled.

FR-01: migration 0007 creates a private `work` schema, append-only synthetic validation records and content-free work-scoped mutation audit. All rows carry workspace UUID; composite keys prevent cross-workspace uniqueness inference. No broad grants/default grants to future tables.
FR-02: trusted development/test CLI explicitly provisions one NOLOGIN, NOINHERIT, non-owner, non-elevated role per workspace and database. No role is a member of another role. Existing family runtime cannot assume these roles or access work objects; work roles cannot access family content, identity records or administration.
FR-03: FORCE RLS binds current database role to its workspace and current database OID; do not trust caller-controlled workspace GUCs. A security-barrier view exposes only the role's active workspace UUID, using the migration owner's underlying registry privileges. Disablement denies future statements. Existing user grant revocation is a separate application gate, not replaced by this service role.
FR-04: insert-only bounded synthetic markers and server-set timestamps; same-transaction audit without marker copies. Deny record/audit mutation/truncate, audit forgery, role escalation, cross-workspace writes and attempts to disable RLS. No public work read/write endpoint or model/connector is added.
FR-05: validate actual PostgreSQL roles/sessions, rollback/audit failure, database-copy isolation and logical restore of work rows/RLS/ACL. Full-host role/key recovery remains distinct. No real data leaves the local environment; Git/CI use synthetic markers only.

Acceptance: family↔work SQL denials, workspace A↔B row/write/role denials, forged settings fail, disabled workspace fails, append-only audit and insert rollback, no credentials/API grants, schema round trip and logical restore. Existing #34 status stays ingestion-disabled; this is not completion of the work-content storage gate or full spec 005.
