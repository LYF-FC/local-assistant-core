# Butler development core

Services: PostgreSQL 17, one-shot Alembic migrations, FastAPI, built React/nginx and Caddy. Windmill/Home Assistant/AI workers are not deployed by this stack.

Caddy publishes 127.0.0.1:8080 by default. PostgreSQL has no host port. API, migrations and web use internal networks; only Caddy joins a non-internal ingress network for host port publishing. No production exposure, egress gateway or remote-model capability is implemented.

From the root: `bash scripts/first-run.sh` creates a development .env with a generated DB password, then builds the shell. Alternatively use `docker compose --env-file .env -p butler-dev -f infra/core/compose.yml up -d --build`. Separate project names, credentials and ports are required for separate environments.

`bash scripts/healthcheck.sh` exits nonzero when core checks fail. /health is Caddy liveness; /api/v1/live is API liveness; /api/v1/health is DB-backed readiness. Inference is optional and does not gate deterministic health. Speech is deliberately unavailable until spec 001.

Stop with `docker compose --env-file .env -p butler-dev -f infra/core/compose.yml down`. Never add -v to a normal stop: it deletes persistent volumes. The CI smoke uses a dedicated disposable project and intentionally deletes only its synthetic volumes.

Active PostgreSQL remains on local storage; Synology is for original documents, archives and protected backups. No backup/production deployment schedule is configured. See ../../docs/BACKUP_RESTORE.md and ../../docs/V0_1_READINESS.md.
