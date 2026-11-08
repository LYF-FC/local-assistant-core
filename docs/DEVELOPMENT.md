# Development and environment isolation

## Toolchain

Python 3.12; uv 0.13.4; Node 22; npm lockfile; Docker Engine/Compose on Linux or compatible macOS runtime. Accelerated AI remains native on the Mac. make check does not require a model, NAS, cloud account or database.

```sh
cd backend
uv sync --locked --extra dev
uv run --locked ruff check .
uv run --locked pytest -m 'not integration' --allow-unix-socket
cd ../frontend
npm ci --ignore-scripts
npm test
npm run build
```

## Isolation

Use separate checkout/worktree, credentials, database, Compose project, port, mailbox/calendar test account and NAS share for each environment. The initial compose supports development/test only; API refuses staging and production. Never copy a production .env or data snapshot into development.

Development: BUTLER_ENV=development, COMPOSE_PROJECT_NAME=butler-dev, port 8080. Test: BUTLER_ENV=test, COMPOSE_PROJECT_NAME=butler-test, port 18080, disposable synthetic DB. Future staging/prod use separately reviewed deployment manifests and secret provisioning after readiness gates pass.

```sh
docker compose --env-file .env -p butler-dev -f infra/core/compose.yml config --quiet
docker compose --env-file .env -p butler-dev -f infra/core/compose.yml up -d --build
```

No shared explicitly named volumes or networks. PostgreSQL remains internal. Only Caddy joins the non-internal ingress network needed for reliable host port publishing on Linux; API, migrations and web stay on internal networks. Never use down -v on a deployment containing valuable records. .env is not sourced as shell code. Treat first-run.sh as a developer helper, not CD.

## Dependency updates

Update manifests and regenerate uv.lock/package-lock.json in a focused PR. Run security audits and full checks; investigate advisories instead of suppressing them globally. Docker uses the committed lock. Base-image tags are versioned but still mutable: digest pinning and automated update review are release blockers documented in readiness.

Keep Spec Kit 1.2.3 setup separate from runtime dependencies. Its existing init script mutates scaffolding and installs extensions; review generated changes. Do not run setup as part of CI or application startup.

## Restricted role changes

The API must run as butler_runtime in development, with a generated runtime password distinct from the migration/admin secret. role_setup is privileged one-shot development provisioning, then exits; API contains only runtime DB credentials. Trusted administration uses migrate. Database fixtures use rollback/savepoints, not deletion of protected audit history. Tests that need concurrent commits use only the explicitly disposable PostgreSQL database and are reset through the destructive migration test. No owner guards are silently disabled for cleanup.
