#!/usr/bin/env bash
set -euo pipefail

log() { printf '\n[butler-bootstrap] %s\n' "$*"; }
die() { printf '\n[butler-bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "This script is for macOS."
[[ "$(uname -m)" == "arm64" ]] || die "Butler production is designed for Apple Silicon (arm64)."

log "Checking Xcode Command Line Tools"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install
  die "Xcode Command Line Tools installation was requested. Re-run this script after it completes."
fi

log "Checking Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  cat <<'EOF'
Homebrew is required but is not installed.

Install it using the official Homebrew installer from:
  https://brew.sh/

Then re-run this script.

We intentionally do not auto-run a remote installer with elevated privileges.
EOF
  exit 2
fi

log "Updating Homebrew metadata"
brew update

log "Installing base packages"
brew install git gh jq curl wget age

log "Installing OrbStack"
if ! command -v orb >/dev/null 2>&1; then
  brew install orbstack
fi

log "Starting OrbStack"
orb start || orb || true

log "Waiting for Docker API"
for i in {1..30}; do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

docker info >/dev/null 2>&1 || die "Docker API is not ready. Open OrbStack once and re-run this script."

log "Creating Butler directories"
mkdir -p "$HOME/Butler"/{backups,exports,logs,models,tmp}
mkdir -p "$HOME/Projects"

cat <<EOF

Host bootstrap complete.

Next:
  ./setup/mac/install-native-ai.sh
  ./scripts/first-run.sh

Persistent local Butler host data:
  $HOME/Butler

Source repositories:
  $HOME/Projects
EOF
