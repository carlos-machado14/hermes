#!/usr/bin/env bash
set -euo pipefail

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH."
  exit 1
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP="$HERMES_HOME/backups/config-pre-token-lean-$(date +%Y%m%d-%H%M%S).yaml"

mkdir -p "$HERMES_HOME/backups"
cp "$HERMES_HOME/config.yaml" "$BACKUP"
echo "Backup: $BACKUP"

# Keep clarify ambient. Every other current Hermes core capability remains available through
# tool_search -> tool_describe -> tool_call instead of paying its full schema on every request.
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
hermes config set agent.execution_guidance compact
hermes config set agent.skills_prompt_mode off

echo
echo "Token-lean tool disclosure configured."
echo "Direct core tool kept: clarify"
echo "Deferred core tools: $(PYTHONPATH="$REPO_ROOT" python3 - <<'PY'
from toolsets import _HERMES_CORE_TOOLS
print(len([name for name in _HERMES_CORE_TOOLS if name != "clarify"]))
PY
)"
echo
echo "Restart gateway:"
echo "  systemctl --user restart hermes-gateway.service"
echo
echo "Then repeat the /v1/chat/completions 'responda apenas ok' test and compare prompt_tokens."
