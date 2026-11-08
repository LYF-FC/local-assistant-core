# Engineering rules

Read `.specify/memory/constitution.md` and the relevant feature contract before meaningful changes. Preserve FastAPI/PostgreSQL/React, explicit scopes, Windmill/Home Assistant boundaries and separately reviewed accelerated/native components.

Use synthetic data only. Never commit private records, credentials, `.env`, runtime exports or host-specific plans. No production access/outbound AI side effect. Use locked uv/npm dependencies and `make check`; permission/migration/audit changes need negative tests and actual disposable PostgreSQL evidence. Keep commit-before-release audit, full restoration tests, real role/idempotence checks and current identity authority.

Use specify/clarify/plan/checklist/tasks/analyze/implement/converge for meaningful work. Canonical context/roadmap/architecture/decisions/operations/setup and feature evidence must agree. Mark merged delivery only after merge with a verified reference; branch engineering and host acceptance are different states.

Prepare coherent batches and local checks before pushing. Use the conservative CI scope policy and mandatory scope/final gate; unknown/critical changes and scheduled/manual events require full coverage. Deliberate skips are not test-pass evidence. Full exact-main evidence and separately reviewed host/recovery gates are required for production/package certification. Keep readonly tokens, SHA-pinned actions, no pull_request_target and no production secrets or database/test-result caches. Record final CI evidence in PR metadata without evidence-only source pushes. Never merge automatically.
