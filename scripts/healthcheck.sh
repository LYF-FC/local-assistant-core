#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo '.env missing; run bash scripts/first-run.sh'; exit 1; }
PORT="$(awk -F= '/^BUTLER_HTTP_PORT=/{print $2}' .env)"
PORT="${PORT:-8080}"
[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && (( 10#$PORT > 0 && 10#$PORT < 65536 )) || { echo 'Invalid HTTP port'; exit 2; }
TLS_PORT="$(awk -F= '/^BUTLER_HTTPS_PORT=/{print $2}' .env)"
TLS_PORT="${TLS_PORT:-8443}"
[[ "$TLS_PORT" =~ ^[0-9]{1,5}$ ]] && (( 10#$TLS_PORT > 0 && 10#$TLS_PORT < 65536 )) || { echo 'Invalid HTTPS port'; exit 2; }
CA_FILE="${BUTLER_LOCAL_CA_FILE:-$HOME/Butler/exports/butler-dev-root.crt}"
failed=0
probe() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '%s: OK\n' "$name"
  else
    printf '%s: DOWN\n' "$name"
    failed=1
  fi
}
probe Docker docker info
probe Caddy curl --max-time 5 -fsS "http://127.0.0.1:$PORT/health"
probe 'API liveness' curl --max-time 5 -fsS "http://127.0.0.1:$PORT/api/v1/live"
probe 'Database readiness' curl --max-time 5 -fsS "http://127.0.0.1:$PORT/api/v1/health"
probe Frontend curl --max-time 5 -fsS "http://127.0.0.1:$PORT/"
probe 'HTTPS certificate/readiness' curl --max-time 5 --cacert "$CA_FILE" -fsS "https://localhost:$TLS_PORT/api/v1/health"
echo 'Speech/runtime capabilities: intentionally blocked pending capability and host acceptance'
exit "$failed"
