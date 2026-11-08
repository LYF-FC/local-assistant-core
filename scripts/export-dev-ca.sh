#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo '.env missing; start the development stack first' >&2; exit 2; }
DESTINATION="${1:-$HOME/Butler/exports/butler-dev-root.crt}"
umask 077
mkdir -p "$(dirname "$DESTINATION")"
docker compose --env-file .env -f infra/core/compose.yml cp caddy:/data/caddy/pki/authorities/local/root.crt "$DESTINATION"
openssl x509 -in "$DESTINATION" -noout -subject -fingerprint -sha256
printf 'Public development CA exported to %s. No trust store was changed.\n' "$DESTINATION"
