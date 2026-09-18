#!/usr/bin/env bash
set -euo pipefail

# Hermes V1 destructive reset.
# Keeps a full backup outside ~/.hermes and extracts only network/Telegram settings
# for the clean local-model installation.
#
# Usage:
#   bash scripts/v1-reset-vps.sh --yes

if [[ "${1:-}" != "--yes" ]]; then
  echo "Refusing destructive reset without --yes."
  echo "Usage: bash scripts/v1-reset-vps.sh --yes"
  exit 2
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$HOME/hermes-v1-backups"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"

mkdir -p "$BACKUP_DIR"

echo "==> Backup directory: $BACKUP_DIR"

if command -v hermes >/dev/null 2>&1; then
  echo "==> Stopping old Hermes gateways"
  hermes gateway stop --all >/dev/null 2>&1 || true
fi

# Last-resort stop for stale gateway processes. Do not touch unrelated services.
pkill -f 'hermes.*gateway' >/dev/null 2>&1 || true
sleep 1

if [[ -d "$HERMES_HOME" ]]; then
  echo "==> Creating full safety backup of $HERMES_HOME"
  tar -C "$(dirname "$HERMES_HOME")" -czf "$BACKUP_DIR/hermes-home-full.tar.gz" "$(basename "$HERMES_HOME")"

  [[ -f "$HERMES_HOME/config.yaml" ]] && cp -a "$HERMES_HOME/config.yaml" "$BACKUP_DIR/config.yaml.full"
  [[ -f "$HERMES_HOME/.env" ]] && cp -a "$HERMES_HOME/.env" "$BACKUP_DIR/env.full"
  [[ -f "$HERMES_HOME/.env" ]] && cp -a "$HERMES_HOME/.env" "$BACKUP_DIR/preserved-full.env"

  if command -v hermes >/dev/null 2>&1; then
    echo "==> Exporting the only active config sections V1 will restore"
    hermes config get network --json > "$BACKUP_DIR/network.json" 2>/dev/null || true
    hermes config get telegram --json > "$BACKUP_DIR/telegram.json" 2>/dev/null || true
  fi

  if [[ -f "$HERMES_HOME/.env" ]]; then
    # Preserve messaging/network routing only. Model/provider credentials are deliberately excluded.
    grep -E '^(TELEGRAM_|GATEWAY_|HERMES_GATEWAY_|HERMES_STARTUP_|HTTP_PROXY=|HTTPS_PROXY=|NO_PROXY=)'       "$HERMES_HOME/.env" > "$BACKUP_DIR/preserved.env" || true
    chmod 600 "$BACKUP_DIR/preserved.env" 2>/dev/null || true
  fi
fi

echo "==> Removing old Ollama models"
if command -v ollama >/dev/null 2>&1; then
  mapfile -t OLLAMA_MODELS < <(ollama list 2>/dev/null | awk 'NR>1 {print $1}' | sed '/^$/d' || true)
  for model in "${OLLAMA_MODELS[@]:-}"; do
    [[ -n "$model" ]] && ollama rm "$model" || true
  done
fi

echo "==> Removing legacy Hermes repositories/state"
rm -rf "$HOME/hermes-local-only"
rm -rf "$HERMES_HOME"

# Intentionally NOT touched:
# - current repository checkout (normally ~/hermes)
# - SSH, firewall/UFW, Docker, Caddy, DNS, system networking
# - $BACKUP_ROOT

mkdir -p "$HERMES_HOME"
chmod 700 "$HERMES_HOME"

# Restore the complete env exactly as it was so user-managed secrets are never lost.
# Provider/model selection is controlled by config.yaml in V1, so old credentials can remain
# stored here without being active.
if [[ -f "$BACKUP_DIR/preserved-full.env" ]]; then
  cp -a "$BACKUP_DIR/preserved-full.env" "$HERMES_HOME/.env"
  chmod 600 "$HERMES_HOME/.env"
fi

cat > "$BACKUP_ROOT/LATEST" <<EOF
$BACKUP_DIR
EOF

echo
echo "Reset complete."
echo "Full backup: $BACKUP_DIR/hermes-home-full.tar.gz"
echo "Preserved config: network.json, telegram.json, preserved.env, preserved-full.env"
echo "Next: follow V1_LOCAL.md from the preserved ~/hermes checkout"
