# 016 — Quarantined synthetic work credential lifecycle

Outcome: a trusted local development/test operator can bootstrap, rotate or revoke one database/workspace-bound login without passing plaintext secrets in arguments, environment, logs, audit or source. The workspace must already have its NOLOGIN storage role and be disabled. Nothing enables a workspace or configures an API adapter.

Permission boundary: privileged host/database operator only, explicit matching development/test environment and disposable butler_test target for tests. No HTTP endpoint, family permission, production access, external model, content ingestion or new dependency. All data remains local.

Bootstrap creates a reserved deterministic login with NOINHERIT/non-elevated flags and exactly one non-admin SET-only storage-role membership. Rotate refuses drift and replaces a client-generated SCRAM verifier, with a 24-hour new-connection password validity. Revoke removes that membership, disables login and clears password; repeated revoke is safe. Workspace remains disabled. DDL and minimal success audit commit together or neither does.

Existing database sessions are not invalidated by password changes. This increment requires stopped consumers and a disabled workspace, rejects observed live login sessions and does not claim a session-termination or activation barrier. Operator must drain/dispose all connections before future activation. No automatic consumer restart or credential persistence: keep generated secrets in the operator's local password manager, never the family memory or Git.

Acceptance: actual TCP password authentication, old-password rejection after rotation, peer/family isolation, drift refusal, disabled-workspace precondition, revoke/repeat revoke, audit rollback and environment/secret-input refusal tests. Existing broker and full CI stay green. Recovery restores no managed login/password automatically; independently review reissue and pool/session revocation before activation.
