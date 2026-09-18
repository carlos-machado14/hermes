#!/usr/bin/env bash
set -euo pipefail

MODEL="qwen3:4b-instruct"
OLLAMA_URL="http://127.0.0.1:11434/v1"
CONTEXT_LENGTH="32768"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed."
  exit 1
fi

ollama pull "$MODEL"

hermes config set model.default "$MODEL"
hermes config set model.provider custom
hermes config set model.base_url "$OLLAMA_URL"
hermes config set model.context_length "$CONTEXT_LENGTH"

hermes config set cron.model "$MODEL"
hermes config set cron.model_provider custom
hermes config set cron.wrap_response false
hermes config set fallback_providers '[]'

echo
echo "Configured Hermes V1 for local-only inference."
echo "Model: $MODEL"
echo "Endpoint: $OLLAMA_URL"
echo "Context: $CONTEXT_LENGTH"
echo
hermes config get model --json
hermes config get cron --json
ollama list
