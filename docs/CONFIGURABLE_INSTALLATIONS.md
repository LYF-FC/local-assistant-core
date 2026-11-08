# Configurable household installations — approved scope

Owner-approved extension, 8 November 2026. INSTALL-01–12 add requirements to the [register](FEATURE_REGISTER.md), with [dependencies](FEATURE_DEPENDENCIES.md). This is planning only: no configuration interface, feature switch, flexible-member schema, production support or migration is implemented by this document.

## Specify

One maintained software core should support independent household installations. Each household provisions suitable hardware and its own users, configuration, records, credentials, storage and backups. The shared repository contains generic software and synthetic fixtures, never a household's personal parameters or operational records. A user can enable only the capabilities they need, see setup requirements and failures, and adopt tested updates without editing shared source or overwriting private state.

The three layers are shared versioned software, private validated configuration and private operational state. An installation is a running system, not a private Git branch containing secret records. No central hosted account/database, cross-household synchronization, inherited credentials or automatic support guarantee is introduced.

## Identity and onboarding

- Use stable software feature/policy identifiers alongside installation-local household, user and workspace identities. Reinstall/restore/import must distinguish restoration of an existing identity from creating an independent installation. Define collision and foreign-backup handling explicitly.
- Securely establish the first owner without default passwords, open provisioning endpoints or secret-bearing URLs/logs; invitation/recovery paths need expiry, single-use semantics and current authority. Technical administration never implies private-content access.
- Support configurable members, display names, relationships, languages and timezones. Do not assume exactly two adults or one child. Relationship labels, display-name matches and feature activation never create grants implicitly; any child/parent authority must be explicit and reviewed.
- Initial fixed synthetic scope IDs remain the current schema, not a promise of dynamic memberships. Before implementation, define reviewed schema/policy migrations, negative access tests and export/provenance compatibility. Do not remove generic-namespace refusal guards as a shortcut.

## Private configuration and templates

Define a versioned, validated configuration schema with explicit compatibility, safe defaults and unsupported-setting errors. Keep secrets in protected provisioning/storage, referenced rather than copied into public configuration. Provisioning, validation, rotation and revocation must not disclose values in status, audit, ordinary logs, exports or UI errors.

Templates export only an allowlisted non-sensitive setup subset. Exclude credentials, personal records, household/user/workspace IDs, private endpoints/account identifiers and host paths by default. Show a preview; validate schema, dependencies and permissions before applying. Creating an installation from a template generates fresh identities and requires new secret provisioning. A full private backup/restore is a separate authenticated operation, not a shareable template. Preserve explicit private preferences in their protected records/configuration, never as public defaults.

## Feature activation and dependencies

The feature catalogue must expose requested versus effective state, missing prerequisites and safe remediation: disabled, setup-required, ready, enabled, blocked and failed. Define dependency graphs, compatibility and cycle/unknown-key refusal; invalid configuration must not start a partially enabled connector. Resource/hardware availability and credential readiness are part of setup, not assumptions.

Only an authorized current administrator may change installation feature state, with applicable human approval and metadata-only audit. A toggle is not a permission grant. Feature operations still require current account/session, owner/workspace grants, CSRF/transport and transactional audit. Identity, authorization, audit, migration safety and recovery are mandatory foundations and cannot be disabled through ordinary feature controls.

Disabling must enforce the decision server-side and in workers/connectors, not merely hide UI. Stop accepting new active operations, revalidate queued/leased jobs and bound approvals, and handle in-flight effects without reporting false cancellation/success. Surface ambiguous outcomes for reconciliation. Dependency changes need a preview; refuse unsafe disable or an explicitly reviewed dependent shutdown rather than silently cascading. Existing independent core functions remain available.

Disabling is not deletion. Preserve records, provenance, history, cleanup/root bindings and recovery obligations. Define authenticated maintenance/export/forget access separately from normal feature use; do not strand records or bypass grants. Re-enable must recheck permissions, secrets and dependencies; do not replay stale jobs, restore expired approvals or reactivate external dispatch without authorization. Uninstall/purge is a separate reviewed operation with retention, backup and unmanaged-copy limits.

## Updates and existing-installation adoption

Distribute versioned releases with compatibility/manifests, reviewed schema/configuration migrations, backup and rollback/recovery instructions. Updates preserve installation identities, records and private configuration. New features/providers default to inactive pending explicit authorized setup; existing controls must not be reset by upgrade. Specify supported hardware/toolchains and any manual provisioning before claiming self-service usability.

Existing installations require a separate private conversion mapping for users/scopes/workspaces and related records, backed up and rehearsed on an isolated copy. Verify owner/grants, provenance, history, tombstones, jobs/approvals, files/keys and restoration; do not match records by display name or infer authority from family relationships. Review irreversible migration/rollback limits before cutover. Keep legacy source/deployment intact until explicit adoption approval. Shared code updates are not blind merges of unrelated Git histories.

## Acceptance

Implementation must add executable feature/negative tests and actual database, worker, browser, upgrade and restore evidence as appropriate. At minimum:

1. Independently onboard two synthetic households, including one with a different membership structure. Each uses its own identities, database/files/secrets/jobs/backups; cross-household read/write/search/answer/export/worker/credential attempts are denied. An admin still cannot read another user's private content.
2. Start from a documented minimal setup with optional capabilities disabled. Core identity/audit/recovery work; missing credentials, hardware, unknown settings and invalid dependency graphs produce actionable non-secret status and no side effects.
3. Enable a configured feature through authorized controls. Unauthorized, expired-session, CSRF and revoked-grant requests fail; UI visibility alone cannot enable API/worker access. Metadata audit failure prevents the activation change.
4. Disable during queued, leased and in-flight synthetic operations. Prove no newly authorized dispatch, bounded reconciliation of ambiguous effects, preserved records and working protected maintenance. Re-enable does not replay stale intent or bypass current grants. Test dependency/capacity/race failures atomically.
5. Export a setup template and inspect exact contents for secret values, personal records/identities, private host/account details and history. Import it into an independent installation with fresh identities; malformed/incompatible templates refuse without partial provisioning or new grants.
6. Rotate/revoke installation-specific credentials, verify redaction and demonstrate that no other installation is affected. No fixture/template/default credential is reusable as production authority.
7. Upgrade a configured installation and restore its protected backup on an isolated host. Preserve identities/data/preferences and disabled states; refuse incompatible software/configuration and foreign identity bindings safely. Verify rollback limits and failure recovery.
8. Rehearse a synthetic legacy namespace conversion with explicit mapping and cross-reference checks. Missing/ambiguous mappings, stale grants, inaccessible files/keys or failed restoration block adoption. No actual private conversion follows automatically from these tests.

## Plan, tasks and convergence boundary

This low-risk scope change uses specify → plan → tasks → implement → converge for documentation. Record INSTALL-01–12, dependencies, canonical context/architecture/decisions/operations/setup, roadmap and acceptance consistently; preserve all original register IDs; validate counts, links, privacy and repository/CI policy before a single batch push. Owner review/merge is required.

Runtime implementation needs its own full feature specification/clarification, migration and security analysis, bounded delivery plan and fresh evidence. Do not reserve a numbered implementation spec that conflicts with concurrent work. Design configuration/identity boundaries early; independent document batches may continue. Complete this milestone before private-data adoption or a reusable-installation release. No license selection, real account provisioning, external send, private-data migration or production activation is authorized here. No data leaves an installation as a result of this scope change.

Planning convergence: all 135 prior register references are retained, and the register/dependency tables each contain the same 147 unique IDs. Changed-document links/anchors, privacy review, repository invariants and all 14 CI policy tests pass locally. This verifies the documentation projection, not the planned runtime behavior. Exact-head hosted evidence belongs in PR metadata; owner review/merge and all implementation acceptance remain open.
