#!/usr/bin/env bash
set -euo pipefail

MODEL="${BUTLER_SPEECH_MODEL:-phonon:40m-multilingual}"

die() { printf '\n[butler-speech] ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '\n[butler-speech] %s\n' "$*"; }

[[ "$(uname -s)" == "Darwin" ]] || die "Ollama speech POC currently targets macOS."
[[ "$(uname -m)" == "arm64" ]] || die "Phonon in Ollama requires Apple Silicon for this POC."
command -v ollama >/dev/null 2>&1 || die "Ollama is not installed. Run setup/mac/install-native-ai.sh first."

log "Checking Ollama"
ollama --version || true

cat <<EOF

This POC will pull:
  $MODEL

Policy:
- household / Butler use only
- French, Spanish and English
- NOT for business or other commercial output
- the multilingual 40M Phonon model is CC BY-NC 4.0

EOF

log "Pulling $MODEL"
ollama pull "$MODEL"

log "Running a short local TTS smoke test"
TMP_WAV="$(mktemp -t butler-phonon).wav"
curl -fsS http://127.0.0.1:11434/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"voice\":\"default\",\"input\":\"Bonjour, je suis Butler.\",\"response_format\":\"wav\"}" \
  --output "$TMP_WAV"

[[ -s "$TMP_WAV" ]] || die "Speech smoke test returned an empty file."

echo "Speech POC ready."
echo "Test WAV: $TMP_WAV"
echo "Play it with: afplay '$TMP_WAV'"
