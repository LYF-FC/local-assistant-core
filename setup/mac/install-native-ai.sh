#!/usr/bin/env bash
set -euo pipefail

log() { printf '\n[butler-native-ai] %s\n' "$*"; }
die() { printf '\n[butler-native-ai] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "This script is for macOS."
[[ "$(uname -m)" == "arm64" ]] || die "Native AI setup requires Apple Silicon."

log "Installing Ollama if needed"
if ! command -v ollama >/dev/null 2>&1; then
  cat <<'EOF'
Ollama is not installed.

Install the current official macOS release from:
  https://ollama.com/download

The Butler production policy is LOCAL MODELS ONLY:
- do not sign in for cloud inference;
- do not use model names ending in :cloud;
- Butler will later enforce a local-model allowlist at the application layer.

After installing Ollama, re-run this script.
EOF
  exit 2
fi

OLLAMA_BIN="$(command -v ollama)"
PLIST="$HOME/Library/LaunchAgents/com.lyffc.butler.ollama.plist"
LOG_DIR="$HOME/Butler/logs"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

log "Creating launchd service for native Ollama"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.lyffc.butler.ollama</string>

  <key>ProgramArguments</key>
  <array>
    <string>${OLLAMA_BIN}</string>
    <string>serve</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>127.0.0.1:11434</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/ollama.out.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/ollama.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.lyffc.butler.ollama" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.lyffc.butler.ollama"

log "Waiting for local Ollama API"
for i in {1..30}; do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:11434/api/tags >/dev/null ||
  die "Ollama did not become healthy. Check $LOG_DIR/ollama.err.log"

cat <<EOF

Native AI foundation is running.

Ollama:
  http://127.0.0.1:11434

No model is pulled automatically.
We will benchmark/select the production models separately.

Future native candidates, installed only when justified:
- llama.cpp / MLX runtime
- Colibri
- native STT/TTS
- native vision models
EOF
