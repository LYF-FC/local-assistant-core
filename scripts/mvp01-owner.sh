#!/usr/bin/env bash
# Owner-runnable local MVP-01 rehearsal (spec 076): synthetic data, loopback only, single stack.
#   bash scripts/mvp01-owner.sh start | status | rebuild | restart [--kill] | stop | reset
#   bash scripts/mvp01-owner.sh scenario <lookup-unavailable|timeout-after-effect|timeout-before-effect> [on|off]
# Never touches .env, a trust store, other Compose projects or unrelated Docker objects.
# Compatible with the macOS system bash 3.2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="local-assistant-core-mvp01-owner"
DATABASE="butler_test_mvp01_owner"
HTTP_PORT=18081
HTTPS_PORT=18444
SUBNET="172.29.243.0/28"
ORIGIN="https://localhost:${HTTPS_PORT}"
STATE="$ROOT/.local/mvp01-owner"
ENV_FILE="$STATE/mvp01-owner.env"
FIXTURES="$STATE/fixtures"
CA_FILE="$STATE/butler-mvp01-dev-root.crt"
REV_FILE="$STATE/installed-revision.txt"
SOURCE_EML="$ROOT/scripts/mvp01-owner-fixtures/invoice.eml"
EML="$FIXTURES/invoice.eml"
FIXTURE_DAY="2026-11-24"
FIXTURE_ZONE="Europe/Zurich"
EXPECTED_SHA="a1b6c2eb631bfe14e6dbbeed559cba75acb0e5640b820a026110d78aee1a9d97"

say() { printf '%s\n' "$*"; }
die() { printf '\n[mvp01-owner] REFUSED: %s\n' "$*" >&2; exit 1; }

compose() {
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" --profile reminders \
    -f infra/core/compose.yml -f infra/core/answers-synthetic.override.yml -f infra/core/mvp01-owner.override.yml "$@"
}

need_tools() {
  command -v docker >/dev/null 2>&1 || die "docker is not available"
  docker info >/dev/null 2>&1 || die "the Docker engine is not running"
  command -v python3 >/dev/null 2>&1 || die "python3 is required on the host"
  command -v openssl >/dev/null 2>&1 || die "openssl is required on the host"
  command -v curl >/dev/null 2>&1 || die "curl is required on the host"
}

secret() { openssl rand -hex 32; }

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n 1; }

ensure_config() {
  umask 077
  mkdir -p "$STATE" "$FIXTURES"
  chmod 700 "$STATE"
  if [ ! -f "$ENV_FILE" ]; then
    # A volume without its generated credentials cannot be opened: refuse instead of guessing.
    if docker volume ls -q --filter "label=com.docker.compose.project=${PROJECT}" | grep -q .; then
      die "volumes of ${PROJECT} exist but ${ENV_FILE} is missing; run 'reset' (destructive; you type the project name to confirm) to start over. The project name is global on this Mac: this also removes a rehearsal that was started from ANOTHER checkout of this repository"
    fi
    {
      printf 'BUTLER_ENV=test\n'
      printf 'BUTLER_POSTGRES_DB=%s\n' "$DATABASE"
      printf 'BUTLER_POSTGRES_USER=butler\n'
      printf 'BUTLER_POSTGRES_PASSWORD=%s\n' "$(secret)"
      printf 'BUTLER_RUNTIME_PASSWORD=%s\n' "$(secret)"
      printf 'BUTLER_HTTP_PORT=%s\n' "$HTTP_PORT"
      printf 'BUTLER_HTTPS_PORT=%s\n' "$HTTPS_PORT"
      printf 'BUTLER_AUTH_ORIGIN=%s\n' "$ORIGIN"
      printf 'BUTLER_SPEECH_ENABLED=false\n'
      printf 'BUTLER_MVP01_MARKER=%s\n' "synthetic-rehearsal-$(openssl rand -hex 8)"
    } > "$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
  validate_config
}

validate_config() {
  [ "$(env_value BUTLER_ENV)" = "test" ] || die "config BUTLER_ENV must be test"
  [ "$(env_value BUTLER_POSTGRES_DB)" = "$DATABASE" ] || die "config database is not ${DATABASE}"
  [ "$(env_value BUTLER_HTTP_PORT)" = "$HTTP_PORT" ] || die "config HTTP port is not ${HTTP_PORT}"
  [ "$(env_value BUTLER_HTTPS_PORT)" = "$HTTPS_PORT" ] || die "config HTTPS port is not ${HTTPS_PORT}"
  [ "$(env_value BUTLER_AUTH_ORIGIN)" = "$ORIGIN" ] || die "config origin is not ${ORIGIN}"
  [ "$(env_value BUTLER_POSTGRES_PASSWORD)" != "$(env_value BUTLER_RUNTIME_PASSWORD)" ] || die "migration and runtime credentials must differ"
  [ "$(env_value BUTLER_POSTGRES_PASSWORD | awk '{print length($0)}')" -ge 24 ] || die "migration credential too short"
  case "$(env_value BUTLER_MVP01_MARKER)" in synthetic-rehearsal-*) ;; *) die "synthetic marker missing from config" ;; esac
}

running_stack() { [ -f "$ENV_FILE" ] && [ -n "$(compose ps -q caddy 2>/dev/null || true)" ]; }

port_in_use() {
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

preflight() {
  local own=0
  running_stack && own=1
  if [ "$own" = 0 ]; then
    for p in "$HTTP_PORT" "$HTTPS_PORT"; do
      if port_in_use "$p"; then
        local who
        who="$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $1" (pid "$2")"}' | head -n 1 || true)"
        die "loopback port ${p} is already in use by ${who:-another process}; nothing was stopped"
      fi
    done
  fi
  # The fixed app subnet and Caddy's trusted-proxy address cannot be shared by two stacks.
  python3 - "$SUBNET" "$PROJECT" <<'PY' || exit 1
import ipaddress, json, subprocess, sys
subnet, project = ipaddress.ip_network(sys.argv[1]), sys.argv[2]
ids = subprocess.run(["docker", "network", "ls", "-q"], capture_output=True, text=True, check=True).stdout.split()
if ids:
    nets = json.loads(subprocess.run(["docker", "network", "inspect", *ids], capture_output=True, text=True, check=True).stdout)
    for net in nets:
        if (net.get("Labels") or {}).get("com.docker.compose.project") == project:
            continue
        for cfg in (net.get("IPAM") or {}).get("Config") or []:
            try:
                other = ipaddress.ip_network(cfg["Subnet"])
            except (KeyError, ValueError):
                continue
            if other.version == subnet.version and other.overlaps(subnet):
                owner = (net.get("Labels") or {}).get("com.docker.compose.project") or "no Compose project"
                hint = f"docker compose -p {owner} down" if owner != "no Compose project" else f"docker network rm {net['Name']} (after stopping whatever uses it)"
                print(f"\n[mvp01-owner] REFUSED: subnet {subnet} overlaps Docker network '{net['Name']}' ({other}) of Compose project '{owner}'.\n"
                      "Only one stack may use the fixed proxy-trust subnet. Nothing was stopped or removed.\n"
                      f"Stop that environment yourself, WITHOUT -v so its data volumes survive:  {hint}\n"
                      "Then run this command again.", file=sys.stderr)
                sys.exit(1)
PY
}

revision_line() {
  local rev dirty fp
  rev="$(git rev-parse HEAD)"
  if [ -n "$(git status --porcelain)" ]; then
    fp="$( (git diff HEAD; git ls-files --others --exclude-standard | sort) | shasum -a 256 | cut -c1-12)"
    dirty="+uncommitted-changes(fingerprint ${fp})"
  else
    dirty=""
  fi
  printf '%s%s on branch %s' "$rev" "$dirty" "$(git rev-parse --abbrev-ref HEAD)"
}

install_fixture() {
  [ -f "$SOURCE_EML" ] || die "fixture source missing"
  [ "$(shasum -a 256 "$SOURCE_EML" | cut -d' ' -f1)" = "$EXPECTED_SHA" ] || die "repository fixture checksum differs from the documented value"
  if [ ! -f "$EML" ] || ! cmp -s "$SOURCE_EML" "$EML"; then
    cp "$SOURCE_EML" "$EML"
    chmod 600 "$EML"
  fi
}

wait_ca() {
  local i
  for i in $(seq 1 40); do
    if compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$CA_FILE" >/dev/null 2>&1; then
      chmod 644 "$CA_FILE"
      return 0
    fi
    sleep 1
  done
  die "the public development CA could not be exported from Caddy"
}

verify_tls() {
  curl --max-time 15 --fail --silent --show-error --cacert "$CA_FILE" "${ORIGIN}/api/v1/health" >/dev/null \
    || die "HTTPS validation with the exported public CA failed (no certificate bypass is attempted)"
  if curl --max-time 10 --fail --silent "${ORIGIN}/api/v1/health" >/dev/null 2>&1; then
    say "note: this Mac already trusts the rehearsal CA (or the system trusts the certificate)"
  fi
}

prompt_password() {
  if [ -n "${BUTLER_MVP01_OWNER_PASSWORD:-}" ]; then return 0; fi
  [ -t 0 ] || die "a synthetic sign-in password is needed: run interactively (hidden prompt) or set BUTLER_MVP01_OWNER_PASSWORD for this one command"
  local a b
  say ""
  say "Choose a SYNTHETIC sign-in password for the rehearsal user 'mvp01-owner' (14+ characters). Never reuse a real password."
  read -rs -p "Synthetic password: " a; echo
  read -rs -p "Repeat: " b; echo
  [ "$a" = "$b" ] || die "passwords differ"
  [ "${#a}" -ge 14 ] || die "password too short"
  BUTLER_MVP01_OWNER_PASSWORD="$a"
  export BUTLER_MVP01_OWNER_PASSWORD
}

seed_fixture() {
  local state
  state="$(compose run --rm -T -e BUTLER_MVP01_OWNER_PASSWORD migrate python - check < scripts/mvp01-owner-fixtures.py | tail -n 1)"
  case "$state" in
    "owner=exists peer=exists agenda_tasks=2 calendar_sources=1") say "fixture: already seeded (idempotent)"; return 0 ;;
  esac
  say "fixture: seeding (${state})"
  prompt_password
  BUTLER_MVP01_PEER_PASSWORD="$(secret)"
  export BUTLER_MVP01_PEER_PASSWORD
  compose run --rm -T -e BUTLER_MVP01_OWNER_PASSWORD -e BUTLER_MVP01_PEER_PASSWORD migrate python - provision < scripts/mvp01-owner-fixtures.py
  BUTLER_MVP01_OWNER_PASSWORD="$BUTLER_MVP01_OWNER_PASSWORD" BUTLER_MVP01_PEER_PASSWORD="$BUTLER_MVP01_PEER_PASSWORD" \
    python3 scripts/mvp01-owner-seed.py "$ORIGIN" "$CA_FILE"
  unset BUTLER_MVP01_OWNER_PASSWORD BUTLER_MVP01_PEER_PASSWORD
}

print_guide() {
  local fp
  fp="$(openssl x509 -in "$CA_FILE" -noout -fingerprint -sha256 2>/dev/null | sed 's/^.*=//')"
  cat <<GUIDE

================ MVP-01 synthetic invoice rehearsal ================
Environment : ${PROJECT}  (database ${DATABASE}, synthetic data only, loopback only)
Installed   : $(cat "$REV_FILE" 2>/dev/null || echo unknown)
URL         : ${ORIGIN}/   (HTTP probe: http://127.0.0.1:${HTTP_PORT}/health; credentials never sent over HTTP)
Sign in     : user  mvp01-owner   password: the synthetic one you chose (never stored or printed)
Fixture day : ${FIXTURE_DAY} in ${FIXTURE_ZONE}      Currency/amount: EUR 123.45
Fixture file: ${EML}
  SHA-256   : ${EXPECTED_SHA}
  What it is: a synthetic forwarded email, one text attachment (invoice MVP01-2026-001, issuer
              "Synthetic Rehearsal Vendor", dated 2026-11-20, due 2026-12-20, total 123.45 EUR).
Question    : What is the total amount?   (simulated model; it cites the line it retrieves; add 'synthetic-unavailable' to see an explicit unavailable answer)
Simulated   : answer model = fixed script 'synthetic_answer_model' (no real model, no outbound AI);
              calendar = one manual snapshot imported through the real API (no provider);
              filing destination = synthetic METADATA ledger (no copy of the invoice, no real folder or NAS).

Trust the HTTPS certificate yourself (this script never changes a trust store):
  public CA   : ${CA_FILE}
  SHA-256 fp  : ${fp}
  Verify that fingerprint, then import the file in Keychain Access (login keychain) and set it to
  "Always Trust" for this local CA, for example:  open -a "Keychain Access" "${CA_FILE}"
  To retire it later, delete that exact fingerprint from the keychain.

Ordered steps
 1  Open ${ORIGIN}/ and sign in as mvp01-owner (no certificate warning should be bypassed).
 2  Open the daily overview for ${FIXTURE_DAY} (${FIXTURE_ZONE}): expect the event "MVP-01 synthetic: family planning call"
    (10:00-11:00 local) and the task "MVP-01 synthetic: pay-check invoice MVP01-2026-001" (due 17:00) once each, and no PEER-PRIVATE-MARKER.
 3  Documents > Import forwarded email: choose ${EML}; import it twice. Expect one document and "Exact email already imported".
 4  Open the document, review its source (correct and review), inspect the email original.
 5  Ask the question above in the answers panel; expect the exact quotation "Total: 123.45" cited at line 5 with document, revision and SHA-256, and a link to the current source.
 6  In-app reminders are enabled by default (preferences are only for different quiet hours or limits). In Tasks and agenda, select the task and use the 'Remind me in Butler' control at the bottom of its details to schedule a reminder a couple of minutes ahead; the reminder worker delivers it once; acknowledge it (the task stays open).
 7  Invoice field review: prepare candidates, confirm issuer/number/issue date/total/currency, leave Due date Unknown, save; suggest and approve the filing plan only.
 8  "Synthetic filing execution": tick both acknowledgements and request the filing; watch Pending -> Filed and open its history.
 9  bash scripts/mvp01-owner.sh restart   (container restart)   then   bash scripts/mvp01-owner.sh restart --kill   (process kill).
    Sign in again; records, review, plan and the filed status are unchanged and no second effect exists (see 'status').
Optional failure rehearsals (synthetic ledger controls): bash scripts/mvp01-owner.sh scenario timeout-after-effect on  (before step 8)
Stop (keeps data and certificate): bash scripts/mvp01-owner.sh stop     Destructive reset of ONLY this rehearsal: bash scripts/mvp01-owner.sh reset
=====================================================================
GUIDE
}

cmd_start() {
  need_tools
  ensure_config
  preflight
  install_fixture
  revision_line > "$REV_FILE"
  say "[mvp01-owner] building and starting ${PROJECT} (images are built from this checkout; rebuild after edits)"
  compose up -d --build --wait --wait-timeout 300
  wait_ca
  verify_tls
  seed_fixture
  print_guide
}

cmd_rebuild() {
  need_tools
  ensure_config
  preflight
  install_fixture
  revision_line > "$REV_FILE"
  say "[mvp01-owner] rebuilding images and recreating containers; named volumes (database, certificates, synthetic ledger) are preserved"
  compose build
  compose up -d --force-recreate --wait --wait-timeout 300
  wait_ca
  verify_tls
  seed_fixture
  print_guide
}

cmd_restart() {
  need_tools
  ensure_config
  running_stack || die "the rehearsal is not running; use 'start'"
  local services="api web caddy reminder_worker filing_worker synthetic_answer_model"
  if [ "${1:-}" = "--kill" ]; then
    say "[mvp01-owner] PROCESS KILL (SIGKILL) of: api reminder_worker filing_worker synthetic_answer_model, then recreate/start"
    compose kill -s SIGKILL api reminder_worker filing_worker synthetic_answer_model
    compose up -d --wait --wait-timeout 300
  else
    say "[mvp01-owner] CONTAINER RESTART of: ${services} (PostgreSQL stays up; this is not a host reboot)"
    # shellcheck disable=SC2086
    compose restart $services
    compose up -d --wait --wait-timeout 300
  fi
  verify_tls
  say "[mvp01-owner] done. Sign in again if needed; run 'status' to compare the ledger counts."
}

cmd_stop() {
  need_tools
  [ -f "$ENV_FILE" ] || die "nothing to stop (no ${ENV_FILE})"
  validate_config
  compose down --remove-orphans
  say "[mvp01-owner] stopped. Database, certificate authority and synthetic ledger volumes are preserved."
}

cmd_status() {
  need_tools
  say "environment : ${PROJECT} / database ${DATABASE}"
  say "URL         : ${ORIGIN}/  (HTTP ${HTTP_PORT})"
  say "checkout    : $(revision_line)"
  say "installed   : $(cat "$REV_FILE" 2>/dev/null || echo 'not built')"
  if [ "$(cat "$REV_FILE" 2>/dev/null || true)" != "$(revision_line)" ]; then say "note        : the checkout differs from the installed build; run 'rebuild' to apply edits"; fi
  if [ ! -f "$ENV_FILE" ]; then say "state       : not initialized"; return 0; fi
  validate_config
  if ! running_stack; then say "state       : stopped"; return 0; fi
  compose ps --format 'table {{.Service}}\t{{.Status}}' || true
  say "fixture     : ${EML} sha256 $(shasum -a 256 "$EML" 2>/dev/null | cut -d' ' -f1) (expected ${EXPECTED_SHA})"
  [ -f "$CA_FILE" ] && say "public CA   : ${CA_FILE} $(openssl x509 -in "$CA_FILE" -noout -fingerprint -sha256 | sed 's/^.*=//')"
  compose run --rm -T migrate python - identity < scripts/mvp01-owner-fixtures.py 2>/dev/null | tail -n 1 || true
  compose run --rm -T migrate python - check < scripts/mvp01-owner-fixtures.py 2>/dev/null | tail -n 1 || true
  say "ledger      : $(compose exec -T filing_worker python -m app.synthetic_ledger status 2>/dev/null || echo unavailable)"
}

cmd_scenario() {
  need_tools
  running_stack || die "the rehearsal is not running"
  case "${1:-}" in lookup-unavailable|timeout-after-effect|timeout-before-effect) ;; *) die "unknown scenario" ;; esac
  compose exec -T filing_worker python -m app.synthetic_ledger control "$1" "${2:-on}"
}

cmd_reset() {
  need_tools
  [ "$PROJECT" = "local-assistant-core-mvp01-owner" ] || die "unexpected project name"
  local have_config=0
  if [ -f "$ENV_FILE" ]; then
    validate_config
    have_config=1
  fi
  # Every object to be removed must belong to this exact Compose project (label AND name prefix).
  local volumes containers
  volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=${PROJECT}")"
  containers="$(docker ps -a --format '{{.Names}}' --filter "label=com.docker.compose.project=${PROJECT}")"
  for v in $volumes; do
    case "$v" in "${PROJECT}_"*) ;; *) die "volume ${v} is not prefixed by ${PROJECT}" ;; esac
  done
  if [ "$have_config" = 0 ] && [ -z "$volumes" ] && [ -z "$containers" ]; then
    die "no rehearsal configuration and no ${PROJECT} containers or volumes found; nothing to reset"
  fi
  say "This will PERMANENTLY delete the disposable synthetic rehearsal:"
  say "  project    : ${PROJECT}"
  say "  database   : ${DATABASE} (volume ${PROJECT}_postgres_data)"
  say "  also       : volumes of that project only (Caddy CA, synthetic filing ledger), its containers/network"
  say "  local files: ${STATE} (generated credentials, exported public CA, fixture copy)"
  say "  containers : $(echo "$containers" | tr '\n' ' ')"
  say "  volumes    : $(echo "$volumes" | tr '\n' ' ')"
  [ "$have_config" = 1 ] || say "  note       : the generated config is missing; the project is removed by its exact Compose label and name prefix"
  say "The project name is global on this Mac: this also removes a rehearsal that was started from ANOTHER checkout."
  say "Nothing else is removed (no prune, no other project, no images)."
  local answer="${BUTLER_MVP01_RESET_CONFIRM:-}"
  if [ -z "$answer" ]; then
    [ -t 0 ] || die "reset needs an interactive terminal (or BUTLER_MVP01_RESET_CONFIRM=${PROJECT})"
    read -r -p "Type the project name to confirm: " answer
  fi
  [ "$answer" = "$PROJECT" ] || die "confirmation did not match; nothing was deleted"
  if [ "$have_config" = 1 ]; then
    compose down -v --remove-orphans
  else
    # Compose only needs the required variables present for interpolation; `down` never uses their values.
    BUTLER_POSTGRES_PASSWORD=reset-only-unused BUTLER_RUNTIME_PASSWORD=reset-only-unused \
      docker compose --env-file /dev/null -p "$PROJECT" --profile reminders \
      -f infra/core/compose.yml -f infra/core/answers-synthetic.override.yml -f infra/core/mvp01-owner.override.yml \
      down -v --remove-orphans
  fi
  rm -rf "$STATE"
  say "[mvp01-owner] reset complete. Remove the old CA fingerprint from your keychain yourself if you imported it."
}

case "${1:-}" in
  start) cmd_start ;;
  status) cmd_status ;;
  rebuild) cmd_rebuild ;;
  restart) shift; cmd_restart "${1:-}" ;;
  stop) cmd_stop ;;
  reset) cmd_reset ;;
  scenario) shift; cmd_scenario "$@" ;;
  *) say "usage: bash scripts/mvp01-owner.sh start|status|rebuild|restart [--kill]|stop|reset|scenario <name> [on|off]"; exit 2 ;;
esac
