#!/usr/bin/env bash
set -euo pipefail

MAIN_MODEL="mimo-v2.5"
MAIN_PROVIDER="opencode-go"
MAIN_BASE_URL="https://opencode.ai/zen/go/v1"
LOCAL_MODEL="qwen3.5:2b-q4_K_M"
LOCAL_BASE_URL="http://127.0.0.1:11434"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is required for the local fast-path."
  exit 1
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
ENV_FILE="$HERMES_HOME/.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! grep -q '^OPENCODE_GO_API_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "Missing OPENCODE_GO_API_KEY in $ENV_FILE."
  echo "Add your OpenCode Go key there first; do not paste it into logs/chat."
  exit 1
fi

echo "Backing up current Hermes config..."
mkdir -p "$HERMES_HOME/backups"
cp "$HERMES_HOME/config.yaml"   "$HERMES_HOME/backups/config-pre-v1-hybrid-$(date +%Y%m%d-%H%M%S).yaml"

if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$LOCAL_MODEL"; then
  echo "Pulling local fast-path model: $LOCAL_MODEL"
  ollama pull "$LOCAL_MODEL"
fi

echo "Configuring main model..."
hermes config set model.default "$MAIN_MODEL"
hermes config set model.provider "$MAIN_PROVIDER"
hermes config set model.base_url "$MAIN_BASE_URL"
hermes config set model.api_mode chat_completions
hermes config unset model.context_length >/dev/null 2>&1 || true

echo "Configuring failover policy..."
hermes config unset agent.reasoning_effort >/dev/null 2>&1 || true
hermes config set fallback_providers '[]'
hermes config set agent.execution_guidance compact
hermes config set agent.skills_prompt_mode off

echo "Configuring progressive tool disclosure..."
DEFER_JSON="$(PYTHONPATH="$REPO_ROOT" python3 - <<'PY'
import json
from toolsets import _HERMES_CORE_TOOLS
print(json.dumps([name for name in _HERMES_CORE_TOOLS if name != "clarify"]))
PY
)"
hermes config set tools.tool_search.enabled on
hermes config set tools.tool_search.listing off
hermes config set tools.tool_search.search_default_limit 5
hermes config set tools.tool_search.max_search_limit 10
hermes config set tools.tool_search.defer "$DEFER_JSON"

echo "Configuring cron model inheritance..."
hermes config unset cron.model >/dev/null 2>&1 || true
hermes config unset cron.model_provider >/dev/null 2>&1 || true
hermes config set cron.wrap_response false

echo "Enabling local reminder fast-path..."
hermes config set local_fastpath.enabled true
hermes config set local_fastpath.model "$LOCAL_MODEL"
hermes config set local_fastpath.base_url "$LOCAL_BASE_URL"
hermes config set local_fastpath.timeout_seconds 15

echo
echo "Hermes V1 hybrid configured."
echo "  Main:       $MAIN_PROVIDER / $MAIN_MODEL"
echo "  Local fast: $LOCAL_MODEL @ $LOCAL_BASE_URL"
echo "  Fallbacks:  disabled"
echo "  Tools:      progressive disclosure (heavy schemas deferred)"
echo "  Cron model: per-job snapshot (no fleet override)"
echo
echo "Restart the native gateway:"
echo "  hermes gateway restart"
