#!/usr/bin/env bash
set -euo pipefail
# Never import a CA into an owner's trust store as an incidental test step.
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_OS:-}" == Linux && "${BUTLER_BROWSER_TESTS:-}" == 1 && "${BUTLER_ENV:-}" == test ]] || exit 2
[[ -f "${BUTLER_CI_CA_FILE:-}" ]] || exit 2
[[ "${NODE_TLS_REJECT_UNAUTHORIZED:-1}" != 0 ]] || exit 2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Chromium M146+ uses the new location; older/existing installations use legacy.
for BUTLER_NSS_PATH in "$HOME/.pki/nssdb" "$HOME/.local/share/pki/nssdb"; do
  mkdir -p "$BUTLER_NSS_PATH"
  [[ -f "$BUTLER_NSS_PATH/cert9.db" ]] || certutil -N -d "sql:$BUTLER_NSS_PATH" --empty-password
  certutil -A -d "sql:$BUTLER_NSS_PATH" -n ButlerSyntheticCI -t 'C,,' -i "$BUTLER_CI_CA_FILE"
done
cleanup() {
  for BUTLER_NSS_PATH in "$HOME/.pki/nssdb" "$HOME/.local/share/pki/nssdb"; do
    certutil -D -d "sql:$BUTLER_NSS_PATH" -n ButlerSyntheticCI || true
  done
}
trap cleanup EXIT
cd "$ROOT/frontend"
# Playwright route.fetch uses Node's TLS store, not Chromium's NSS store.
# Verify untrusted Node requests fail, then trust only this public CI root for
# these child processes. Never disable certificate verification or change host trust.
if env -u NODE_EXTRA_CA_CERTS node -e 'fetch(process.env.BUTLER_E2E_ORIGIN + "/api/v1/health").then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))' >/dev/null 2>&1; then
  echo 'Unexpected Node global trust of synthetic CA' >&2; exit 1
fi
NODE_EXTRA_CA_CERTS="$BUTLER_CI_CA_FILE" node -e 'fetch(process.env.BUTLER_E2E_ORIGIN + "/api/v1/health").then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))'
NODE_EXTRA_CA_CERTS="$BUTLER_CI_CA_FILE" npm run test:e2e -- "$@"
