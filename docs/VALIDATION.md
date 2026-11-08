# Validation status

## Verified public baseline — 8 November 2026

Public source revision: [`501d92ba739c57768caff130ce8a216056cbde5d`](https://github.com/LYF-FC/local-assistant-core/commit/501d92ba739c57768caff130ce8a216056cbde5d).

[Foundation CI run 42480415480](https://github.com/LYF-FC/local-assistant-core/actions/runs/42480415480) completed successfully on that revision. Its six jobs — scope, backend, frontend, PostgreSQL, containers and final ci gate — all succeeded. This is public engineering evidence from synthetic infrastructure, not an inherited private acceptance claim.

| Check | Baseline result |
|---|---|
| Repository and CI policy | Passed, including 14 policy tests |
| Backend | 847 unit tests; formatting/security/dependency checks passed |
| Frontend | 357 tests, production build and dependency audit passed |
| PostgreSQL | 693 integration cases, including namespace refusal and permission checks |
| Logical recovery | Complete synthetic backup/restore/recovery drill passed |
| Containers/browser | 59 general plus 22 Work scenarios: all 81 passed; transport/container/recovery assertions passed |
| Final gate | Passed, with all selected product jobs successful |

The earlier statement that the complete hosted browser suite was pending is superseded by this run. Earlier local verification covered 71 distinct portable browser scenarios and other local checks; it is separate dated evidence. Test warnings existed; this is not a warning-free claim.

## Evidence limits and future updates

The [register](FEATURE_REGISTER.md) maps bounded specs to partial capability evidence. Literal cited excerpts are not generated answers; text/Markdown BYTEA staging is not PDF/OCR/durable archive; in-app reminders are not external delivery; no-op/synthetic workers are not live connectors; synthetic Work recovery does not certify all archive/key/full-host recovery.

Full MVP, staging/production startup, actual mobile/private-host/provider use, real records and independent clean-host/key/source/latest-backup recovery remain unaccepted. See [MVP acceptance](MVP_ACCEPTANCE.md) and [readiness](V0_1_READINESS.md). Generic namespace checks refuse mismatched databases before mutation; they are not a private-data conversion procedure.

New PRs must record local results and final exact-head CI evidence in PR metadata. The conservative selector requires policy plus final gate for documentation-only work and full product coverage for critical/unknown paths. Intentional unselected jobs are not passing tests. Production/package certification requires full successful coverage on its exact main revision plus independently reviewed security/deployment/recovery acceptance. Do not push source-only evidence updates after otherwise final checks.
