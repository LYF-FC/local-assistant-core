# CI scope and compute

PRs use exact merge-base Git comparisons; main pushes compare before/after. Known Markdown-only changes run repository/policy checks. Frontend-only source/configuration/dependencies run frontend and the complete container/browser/recovery job. Backend/security/schema/backend dependencies/infrastructure/CI/governance/unknown changes run all four product jobs. Missing/invalid/unavailable/empty comparisons fall back to full coverage. Deleted rename sources are included. Scheduled/manual runs are full.

`scope` and the final always-running `ci` gate are mandatory. Missing/failed/cancelled/inconsistent selected evidence fails the gate; deliberate skips are not test-pass evidence. Include `ci` when configuring required checks. Full exact-main evidence is required for production/package certification, with manual dispatch when a narrower main profile is insufficient.

Database schema bootstrap runs once per test module, preserving per-test target guards, fresh pools, repeated runtime-role/idempotence setup and all migration/permission/restore assertions. Parallel role-destructive tests must use separate disposable clusters. Npm caches downloaded packages by lockfile, not node_modules or test state. Weekly minor/patch dependency groups keep normal major/security review behavior. Synthetic screenshots retain the existing one-day policy.

Prepare complete changes and local checks before a batch push. Public standard GitHub-hosted runner compute is currently free, while larger-runner/storage/usage rules are separate. No billing or runner policy is changed by this preparation. Source visibility is not a security/release certificate.
