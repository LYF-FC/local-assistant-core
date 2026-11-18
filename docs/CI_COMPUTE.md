# CI scope and compute

PRs use exact merge-base Git comparisons; main pushes compare before/after. Known Markdown-only changes run repository/policy checks. Frontend-only source/configuration/dependencies run frontend and the complete container/browser/recovery job. Backend/security/schema/backend dependencies/infrastructure/CI/governance/unknown changes run all four product jobs. Missing/invalid/unavailable/empty comparisons fall back to full coverage. Deleted rename sources are included. Scheduled/manual runs are full.

`scope` and the final always-running `ci` gate are mandatory. Missing/failed/cancelled/inconsistent selected evidence fails the gate; deliberate skips are not test-pass evidence. Include `ci` when configuring required checks. Full exact-main evidence is required for production/package certification, with manual dispatch when a narrower main profile is insufficient.

Database schema bootstrap runs once per test module, preserving per-test target guards, fresh pools, repeated runtime-role/idempotence setup and all migration/permission/restore assertions. Parallel role-destructive tests must use separate disposable clusters. Npm caches downloaded packages by lockfile, not node_modules or test state. Weekly minor/patch dependency groups keep normal major/security review behavior. Synthetic screenshots retain the existing one-day policy.

Prepare complete changes and local checks before a batch push. Public standard GitHub-hosted runner compute is currently free, while larger-runner/storage/usage rules are separate. No billing or runner policy is changed by this preparation. Source visibility is not a security/release certificate.

## Generated feature documentation

Only `docs/FEATURE_DASHBOARD.html` and `docs/FEATURE_PROGRESS.json` join known Markdown documentation in narrow selection. Repository policy requires exact reproduction by the trusted offline generator/template, matching register/review/stage IDs, known statuses and a verified-snapshot fingerprint. A changed dashboard alone cannot smuggle rendering code: mismatched output fails policy. Neighboring HTML/JSON and generator/template/checker/selector changes remain full, as do bad comparisons and scheduled/manual runs. The initial spec 059 tooling/policy PR therefore requires all six jobs once; later validated metadata-only refreshes need scope/final gate, not product reruns. No workflow permissions, required final gate or scheduled coverage is weakened.


## Picomatch advisory withdrawal — 18 November 2026

The owner authorized an exception if needed to resume implementation on PRs #54–#56.
Before activation, GitHub marked [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
withdrawn on 18 November. Two fresh full audits against the original dependency
lock, including a fresh-cache online check, returned exit 0 and zero findings.
No exception is activated; `npm audit --audit-level=high`, required scope/final
checks and workflow selection remain unchanged. No dependency or package identity
change was needed for those audit results. Withdrawal is not a source-code fix or
proof of whole-toolchain safety. Retain failed historical results and require fresh
exact-head CI before merging the refreshed recovery work. See the later
[owner decision](../DECISIONS.md#18-november-2026--owner-authorizes-resuming-implementation-advisory-withdrawal-makes-an-exception-unnecessary).
