#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\n[butler-first-run] %s\n' "$*"; }
die() { printf '\n[butler-first-run] ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker is not available. Make a reviewed local Docker environment available; see SETUP.md."
docker info >/dev/null 2>&1 || die "Docker engine is not running."

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example"
  cp .env.example .env

  if command -v openssl >/dev/null 2>&1; then
    PASSWORD="$(openssl rand -hex 32)"
    perl -0pi -e "s/CHANGE_ME_WITH_A_LONG_RANDOM_VALUE/$PASSWORD/" .env
  fi

  chmod 600 .env
  log "Created local .env. It is intentionally not committed."
fi

if ! grep -q '^BUTLER_RUNTIME_PASSWORD=' .env; then
  command -v openssl >/dev/null 2>&1 || die "openssl is required to generate the runtime secret."
  BUTLER_GENERATED_RUNTIME_PASSWORD="$(openssl rand -hex 32)"
  printf '\nBUTLER_RUNTIME_PASSWORD=%s\n' "$BUTLER_GENERATED_RUNTIME_PASSWORD" >> .env
fi
if grep -q '^BUTLER_RUNTIME_PASSWORD=CHANGE_ME' .env; then
  command -v openssl >/dev/null 2>&1 || die "openssl is required to generate the runtime secret."
  BUTLER_GENERATED_RUNTIME_PASSWORD="$(openssl rand -hex 32)"
  perl -0pi -e "s/CHANGE_ME_RUNTIME_WITH_A_LONG_RANDOM_VALUE/$BUTLER_GENERATED_RUNTIME_PASSWORD/" .env
fi
chmod 600 .env
if grep -Eq '^BUTLER_(POSTGRES|RUNTIME)_PASSWORD=.*CHANGE_ME' .env; then
  die "Set BUTLER_POSTGRES_PASSWORD in .env before continuing."
fi

log "Building and starting Butler v0.1"
docker compose --env-file .env -f infra/core/compose.yml up -d --build

PORT="$(awk -F= '/^BUTLER_HTTP_PORT=/{print $2}' .env 2>/dev/null || true)"
PORT="${PORT:-8080}"

log "Waiting for Butler API through Caddy"
for i in {1..45}; do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:$PORT/api/v1/health" ||
  die "Butler API did not become healthy. Run docker compose logs to inspect the stack."
printf '\n'

log "Checking frontend"
curl -fsS "http://127.0.0.1:$PORT/" >/dev/null ||
  die "Butler frontend is not reachable."

log "Exporting public development CA and verifying HTTPS"
BUTLER_FIRST_RUN_CA_FILE="${BUTLER_LOCAL_CA_FILE:-$HOME/Butler/exports/butler-dev-root.crt}"
bash scripts/export-dev-ca.sh "$BUTLER_FIRST_RUN_CA_FILE"
TLS_PORT="$(awk -F= '/^BUTLER_HTTPS_PORT=/{print $2}' .env 2>/dev/null || true)"
TLS_PORT="${TLS_PORT:-8443}"
curl --max-time 10 --fail --silent --show-error --cacert "$BUTLER_FIRST_RUN_CA_FILE" "https://localhost:$TLS_PORT/api/v1/health" || die "HTTPS validation failed."
printf '\n'

cat <<EOF

Butler development foundation is up (not production-ready).

Open:
  https://localhost:$TLS_PORT/ (import the exported public development CA before browser sign-in)

Current stack:
- PostgreSQL 17
- Alembic migration runner
- FastAPI backend v0.1
- React/TypeScript frontend v0.1
- Caddy reverse proxy
- restricted-role setup and loopback HTTPS/sign-in UI
- scoped Memory inspection/correction/history/export/forgetting UI
- manual private Discovery proposals and feedback

Still intentionally deferred:
- actual M2 browser/CA acceptance (HTTP identity requests stay denied)
- inference, retrieval, speech/model installation and live data imports
- Windmill
- observability
- specialist domain APIs, Discovery collectors and Work Companion data ingestion

Run:
  bash scripts/healthcheck.sh
EOF

