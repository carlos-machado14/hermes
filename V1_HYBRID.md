# Hermes/Freud V1 — Hybrid

This is the preferred V1 profile.

```text
Telegram / Freud API
   |
   v
Hermes native gateway
   |
   +-- explicit simple reminder/routine action --> local fast-path
   |                                                |
   |                                                v
   |                                      Qwen3.5 2B / Ollama
   |                                      tiny JSON-only parser
   |                                                |
   |                                                v
   |                                      native Hermes cron
   |                                      no_agent static delivery
   |                                      (zero LLM at fire time)
   |
   +-- conversation / ambiguity / research / web --> MiMo-V2.5
                                                    OpenCode Go
                                                    |
                                                    +-- progressive tool disclosure
                                                    +-- web/browser
                                                    +-- memory/tasks
                                                    +-- intelligent cron
```

There is no separate router daemon, no parallel scheduler, and no custom cron service.
Routing lives inside the existing Hermes gateway and native cron remains the only scheduler.

## Routing rules

The local path is intentionally narrow and fail-open.

Examples that should use the local path:

- `Me lembre amanhã às 10h de revisar minhas tarefas.`
- `Me cobre a cada 2 horas para beber água.`
- `Quais são minhas rotinas?`
- `Pause a rotina Beber água.`

Examples that must stay on the main MiMo agent:

- `Pesquise a versão atual do Flutter.`
- `Procure vagas Flutter remotas.`
- `Crie uma rotina que pesquise vagas Flutter todos os dias e me mande as melhores.`
- ambiguous requests or anything the local parser cannot validate.

A static reminder may mention a future human action such as
`Me lembre amanhã de pesquisar vagas`; it is still a static reminder and does not require web
access when it fires.

## Failure behavior

The fast-path never blocks the assistant. If the local Qwen times out, returns malformed JSON,
selects an unsupported action, or produces a schedule rejected by native cron validation, Hermes
falls through to the normal MiMo agent.

## Models

Main:

```text
provider: opencode-go
model: mimo-v2.5
```

Local parser:

```text
qwen3.5:2b-q4_K_M
http://127.0.0.1:11434
```

The local parser uses a small 4K context and JSON-only output. It does not receive the full Hermes
system prompt or the web/browser schemas.

## Token budget / progressive tools

The full Hermes tool surface is intentionally **not** sent to MiMo on every turn.

V1 enables Hermes' native `tool_search` progressive disclosure and keeps only `clarify`
ambient. The remaining core capabilities are deferred and are reached through:

```text
tool_search -> tool_describe -> tool_call
```

This preserves the capabilities while removing the large terminal/browser/file/skills/cron/etc.
schemas from trivial requests. The embedded deferred-tool manifest is disabled
(`tools.tool_search.listing=off`) so the baseline prompt stays small.

The optimization deliberately does **not** disable execution guidance or memory injection yet.
Those are quality-sensitive and should only be dieted after measuring the savings from tool
deferral.

For an already-configured V1:

```bash
bash scripts/v1-optimize-token-budget.sh
systemctl --user restart hermes-gateway.service
```

Then repeat a fresh-session API call such as `responda apenas ok` and compare
`usage.prompt_tokens` with the previous baseline.

## Cron behavior

Static reminders created by the fast-path use `no_agent=True` with a static prompt. At fire time
the native Hermes scheduler delivers that prompt verbatim. No cloud or local LLM is called.

Dynamic cron jobs remain agent-backed. V1 deliberately leaves the fleet-wide `cron.model` and
`cron.model_provider` overrides unset: existing jobs keep their creation-time model snapshots,
while newly-created intelligent jobs snapshot the current main model (MiMo-V2.5). This avoids
silently moving old simple jobs onto paid inference while still giving new web/research routines
the capable model.

## Configuration

Reference: `config/v1-hybrid.yaml.example`.

For an existing V1 server:

```bash
bash scripts/v1-configure-hybrid.sh
```

The script preserves Telegram/toolset configuration and does not modify `~/.hermes/.env`.
It requires an existing `OPENCODE_GO_API_KEY`.

## Acceptance tests

After deployment and gateway restart:

1. `Responda somente: OK`
   - main MiMo path; baseline token count should be materially lower than the eager-tool configuration.
2. `Me lembre em 5 minutos de testar o Hermes`
   - local fast-path; should create a short-title static no-agent cron.
3. `Quais são minhas rotinas?`
   - deterministic local list; no LLM.
4. `Pesquise na internet qual é a versão estável atual do Flutter e responda curto.`
   - main MiMo; the model discovers the web capability on demand.
5. `Crie uma rotina diária que pesquise vagas Flutter novas e me mande as melhores.`
   - main MiMo; cron tooling is discovered on demand and the resulting cron must be agent-backed.

Inspect with:

```bash
hermes cron list
journalctl --user -u hermes-gateway.service -f
```
