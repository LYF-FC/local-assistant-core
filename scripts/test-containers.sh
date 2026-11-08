#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export BUTLER_ENV=test
export BUTLER_POSTGRES_PASSWORD=synthetic-ci-only-password-0123456789
export BUTLER_POSTGRES_DB=butler_test_container
export BUTLER_RUNTIME_PASSWORD=synthetic-runtime-only-password-0123456789
export BUTLER_HTTP_PORT=18080
export BUTLER_HTTPS_PORT=18443
export BUTLER_AUTH_ORIGIN=https://localhost:18443
export BUTLER_E2E_ORIGIN=https://localhost:18443
export BUTLER_E2E_HTTP_ORIGIN=http://127.0.0.1:18080
BUTLER_CI_CA_DIR=$(mktemp -d)
export BUTLER_CI_CA_FILE="$BUTLER_CI_CA_DIR/root.crt"
export COMPOSE_PROJECT_NAME=butler-ci
export BUTLER_SPEECH_ENABLED=false
compose() { docker compose -f infra/core/compose.yml "$@"; }
pdf_compose() { docker compose -f infra/core/compose.yml -f infra/core/document-archive.override.yml -f infra/core/pdf-ingestion.override.yml "$@"; }
answers_compose() { docker compose -f infra/core/compose.yml -f infra/core/answers-synthetic.override.yml "$@"; }
archive_compose() { docker compose -f infra/core/compose.yml -f infra/core/document-archive.override.yml "$@"; }
synthetic_compose() { docker compose -f infra/core/compose.yml -f infra/core/work-synthetic.override.yml "$@"; }
review_compose() { docker compose -f infra/core/compose.yml -f infra/core/work-synthetic.override.yml -f infra/core/work-draft-review.override.yml -f infra/core/work-draft-confirmation.override.yml -f infra/core/work-context-preview.override.yml -f infra/core/work-synthetic-capture.override.yml -f infra/core/work-note-changes.override.yml -f infra/core/work-notes-interface.override.yml "$@"; }
cleanup() {
  status=$?
  set +e
  if [[ "$status" != 0 ]]; then compose logs --no-color --tail 80; fi
  answers_compose down --volumes --remove-orphans
  pdf_compose down --volumes --remove-orphans
  archive_compose down --volumes --remove-orphans
  synthetic_compose down --volumes --remove-orphans
  rm -rf "$BUTLER_CI_CA_DIR"
  return "$status"
}
trap cleanup EXIT
compose config --quiet
compose up --build -d --wait --wait-timeout 180
curl --fail --silent --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:18080/api/v1/live
curl --fail --silent http://127.0.0.1:18080/api/v1/health
curl --fail --silent http://127.0.0.1:18080/ >/dev/null
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18080/api/v1/speech/synthesize)
[[ "$STATUS" == 503 ]]
[[ "$(compose exec -T api id -u)" == 10001 ]]
[[ "$(compose exec -T web id -u)" == 101 ]]
# Export only the public CA; never export the volume or a private key.
compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$BUTLER_CI_CA_FILE"
curl --fail --silent --cacert "$BUTLER_CI_CA_FILE" "$BUTLER_E2E_ORIGIN/api/v1/health"
# The TLS CA is deliberately not trusted by the system curl store.
if curl --fail --silent "$BUTLER_E2E_ORIGIN/api/v1/health" >/dev/null 2>&1; then
  echo 'Unexpected global trust of synthetic CA' >&2; exit 1
fi
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H "Origin: $BUTLER_AUTH_ORIGIN" -H 'X-Forwarded-Proto: https' -H 'X-Forwarded-For: 198.51.100.5' -d '{}' http://127.0.0.1:18080/api/v1/auth/session)
[[ "$STATUS" == 400 ]]
STATUS=$(curl --cacert "$BUTLER_CI_CA_FILE" -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H 'Origin: https://other.invalid' -d '{}' "$BUTLER_E2E_ORIGIN/api/v1/auth/session")
[[ "$STATUS" == 403 ]]
# A data-network peer cannot impersonate Caddy by supplying forwarding headers.
compose run --rm -T migrate python - <<'PY'
import urllib.request, urllib.error
request=urllib.request.Request('http://api:8000/api/v1/auth/session', data=b'{}', headers={'Content-Type':'application/json','Origin':'https://localhost:18443','Host':'localhost:18443','X-Forwarded-Proto':'https'})
try:
    urllib.request.urlopen(request,timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 400
else:
    raise AssertionError('Untrusted forwarding headers were accepted')
PY
if [[ "${BUTLER_BROWSER_TESTS:-0}" == 1 ]]; then
  compose run --rm -T migrate python - seed < scripts/browser-fixtures.py
  # The optional reminder service remains stopped by default; exercise two actual one-shot processes.
  [[ -z "$(compose ps --status running --services | sed -n '/^reminder_worker$/p')" ]]
  compose --profile reminders build reminder_worker
  [[ "$(compose --profile reminders run --rm -T --no-deps reminder_worker id -u)" == 10001 ]]
  compose run --rm -T migrate python - seed < scripts/reminder-browser-fixtures.py
  compose --profile reminders run --rm -T --no-deps reminder_worker python -m app.reminder_worker --once
  compose --profile reminders run --rm -T --no-deps reminder_worker python -m app.reminder_worker --once
  compose run --rm -T migrate python - check < scripts/reminder-browser-fixtures.py
  if compose --profile reminders run --rm -T --no-deps reminder_worker python - check < scripts/reminder-browser-fixtures.py >/dev/null 2>&1; then
    echo 'Runtime account unexpectedly accepted the privileged synthetic fixture' >&2; exit 1
  fi
  bash scripts/test-ci-browser.sh
  # Separate opt-in archive phase, with a fresh bounded synthetic identity budget.
  compose down --volumes --remove-orphans
  archive_compose up -d --wait --wait-timeout 180
  archive_compose run --rm -T --no-deps api python -m app.document_archive /var/lib/butler-document-archive
  archive_compose run --rm -T migrate python - seed < scripts/browser-fixtures.py
  archive_compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$BUTLER_CI_CA_FILE"
  BUTLER_DOCUMENT_ARCHIVE_BROWSER_TESTS=1 bash scripts/test-ci-browser.sh document-archive.spec.ts
  archive_compose down --volumes --remove-orphans
  # Explicit offline parser phase: no database credentials, TCP network or archive mount in worker.
  pdf_compose up --build -d --wait --wait-timeout 240
  pdf_compose run --rm -T --no-deps api python -m app.document_archive /var/lib/butler-document-archive
  pdf_compose run --rm -T migrate python - seed < scripts/browser-fixtures.py
  PDF_WORKER_ID=$(pdf_compose ps -q pdf_worker)
  [[ "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$PDF_WORKER_ID")" == none ]]
  [[ "$(pdf_compose exec -T pdf_worker id -u)" == 10001 ]]
  pdf_compose exec -T pdf_worker python - <<'PYPDFPARENT'
try:
    with open('/proc/1/mem', 'rb') as source:
        source.read(1)
except PermissionError:
    print('Parser parent memory is protected')
else:
    raise AssertionError('Parser parent memory was readable')
PYPDFPARENT
  if pdf_compose exec -T pdf_worker env | sed -n '/^BUTLER_POSTGRES_/p' | read -r _; then
    echo 'Parser unexpectedly received database configuration' >&2; exit 1
  fi
  python3 scripts/pdf-worker-cases.py > "$BUTLER_CI_CA_DIR/pdf-cases.json"
  pdf_compose run --rm -T --no-deps -v "$PWD/scripts/pdf-worker-checks.py:/opt/check.py:ro" pdf_worker python /opt/check.py < "$BUTLER_CI_CA_DIR/pdf-cases.json"
  pdf_compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$BUTLER_CI_CA_FILE"
  BUTLER_PDF_BROWSER_TESTS=1 BUTLER_PDF_BROWSER_CASES="$BUTLER_CI_CA_DIR/pdf-cases.json" bash scripts/test-ci-browser.sh pdf-ingestion.spec.ts
  pdf_compose down --volumes --remove-orphans
  # Fresh local-only simulated model phase; no existing host runtime is contacted.
  answers_compose up --build -d --wait --wait-timeout 180
  answers_compose run --rm -T migrate python - seed < scripts/browser-fixtures.py
  answers_compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$BUTLER_CI_CA_FILE"
  BUTLER_ANSWERS_BROWSER_TESTS=1 bash scripts/test-ci-browser.sh answers.spec.ts
  answers_compose down --volumes --remove-orphans
  # Independent disposable acceptance phases must not consume one shared source's
  # 30-login budget as the suite grows. Preserve the real limiter; create a fresh
  # test stack rather than clearing counters, waiting or weakening authentication.
  # All base/default-disabled acceptance checks above remain required.
  compose down --volumes --remove-orphans
  compose up -d --wait --wait-timeout 180
  compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$BUTLER_CI_CA_FILE"
  curl --fail --silent --cacert "$BUTLER_CI_CA_FILE" "$BUTLER_E2E_ORIGIN/api/v1/health"
  if curl --fail --silent "$BUTLER_E2E_ORIGIN/api/v1/health" >/dev/null 2>&1; then
    echo 'Unexpected global trust of fresh synthetic CA' >&2; exit 1
  fi
  compose run --rm -T migrate python - seed < scripts/browser-fixtures.py
  # Explicit synthetic-only adapter overlay; base POC was tested disabled above.
  synthetic_compose run --rm -T migrate python - seed < scripts/work-adapter-fixtures.py
  review_compose run --rm -T migrate python - review < scripts/work-adapter-fixtures.py
  review_compose run --rm -T migrate python - < scripts/work-meeting-fixtures.py
  review_compose up -d --no-deps --wait --wait-timeout 90 api
  BUTLER_CI_REVIEW_DRAFT=$(review_compose run --rm -T migrate python - draft-id < scripts/work-adapter-fixtures.py)
  export BUTLER_CI_REVIEW_DRAFT
  python3 scripts/test-work-adapter-tls.py present
  BUTLER_WORK_NOTES_BROWSER_TESTS=1 bash scripts/test-ci-browser.sh work-notes.spec.ts work-debrief.spec.ts work-export.spec.ts work-meeting.spec.ts work-review.spec.ts
  synthetic_compose run --rm -T migrate python - remove < scripts/work-adapter-fixtures.py
  python3 scripts/test-work-adapter-tls.py missing
fi
compose run --rm -T migrate python - seed < scripts/work-retention-fixtures.py
compose run --rm -T migrate python - container < scripts/work-restore-fixtures.py
compose run --rm -T migrate python - container < scripts/work-suppression-fixtures.py
compose run --rm -T migrate python - container < scripts/work-restored-requests-fixtures.py
compose run --rm -T migrate python - container < scripts/restored-execution-fixtures.py
compose run --rm -T migrate python - container_before < scripts/recovery-assessment-fixtures.py
compose run --rm -T migrate python - container < scripts/restored-session-fixtures.py
compose run --rm -T migrate python - container_after < scripts/recovery-assessment-fixtures.py
compose run --rm -T migrate python - < scripts/restored-credential-fixtures.py
compose run --rm -T migrate python - container < scripts/work-source-withdrawal-fixtures.py
compose run --rm -T migrate python - container < scripts/work-source-checkpoint-fixtures.py
echo "Development TLS/container smoke verified"
