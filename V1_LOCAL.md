# Hermes V1 — local-only

V1 is intentionally small and local:

```
Telegram
   ↓
Hermes
   ↓
Ollama on 127.0.0.1:11434
   ↓
qwen3:4b-instruct
   ↓
conversation OR cronjob_manage
   ↓
native Hermes cron scheduler
```

There is no OmniRoute/OpenRouter fallback in V1.

## Model configuration

Use `config/v1-local.yaml.example` as the reference configuration.

The local runtime is Ollama using its OpenAI-compatible endpoint:

```
http://127.0.0.1:11434/v1
```

Both interactive chat and cron execution use:

```
qwen3:4b-instruct
```

The starting context is 32768 tokens. This is a practical compromise for an 8 GB VPS; increase it
only after measuring memory use.

## Ollama service

Keep the service bound to loopback only and disable cloud features:

```
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_NO_CLOUD=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
```

## Hermes configuration

```bash
hermes config set model.default qwen3:4b-instruct
hermes config set model.provider custom
hermes config set model.base_url http://127.0.0.1:11434/v1
hermes config set model.context_length 32768
hermes config set cron.model qwen3:4b-instruct
hermes config set cron.model_provider custom
hermes config set cron.wrap_response false
hermes config set fallback_providers '[]'
```

## What to preserve from the legacy VPS

Before deleting the old Hermes state, preserve only:

- `network` section from `~/.hermes/config.yaml`;
- `telegram` section from `~/.hermes/config.yaml`;
- the complete `~/.hermes/.env` file, including user-managed secrets;
- `TELEGRAM_*`, `GATEWAY_*`, and `HERMES_GATEWAY_*` are additionally exported separately for inspection.

Do not migrate old cron jobs, plugins, hooks, model/router configuration, memory, provider fallbacks,
or legacy repositories into V1.

Always make a full backup of `~/.hermes` outside that directory before cleanup. The reset script restores the full `.env` after cleanup so custom secrets are preserved. Old provider credentials may remain stored there, but V1 still forces the active model/provider to the local Ollama configuration and keeps `fallback_providers: []`.

## Acceptance test

Send on Telegram:

> Me lembre de beber água a cada 2 horas, das 8h às 18h, de segunda a sexta.

Expected:

- one cron job;
- short semantic title such as `Beber água`;
- native `bounded_interval` schedule;
- local Qwen3 execution;
- pt-BR output;
- delivery to the same Telegram context;
- no technical cron wrapper.
