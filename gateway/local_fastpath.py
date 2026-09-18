"""Hermes V1 local fast-path for cheap, explicit reminder/routine actions.

The main agent remains authoritative for conversation, research, web/browser work and
ambiguous requests.  This module only wakes the local Ollama model after a deterministic
prefilter has identified an explicit reminder/routine-management request.

Fail-open rule: any timeout, malformed local-model output, unsupported action or cron
validation failure returns None so the normal main-agent path handles the message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_CREATE_MARKERS = (
    "me lembre", "me lembra", "me lembrar", "lembre-me",
    "me avise", "me avisa", "me avisar", "me cobre",
    "crie um lembrete", "criar um lembrete", "crie uma rotina",
    "criar uma rotina", "agende", "programe",
)
_ROUTINE_WORDS = ("rotina", "rotinas", "lembrete", "lembretes", "cron", "crons")
_MANAGE_MARKERS = (
    "liste", "listar", "mostre", "mostrar", "quais",
    "pause", "pausar", "retome", "retomar", "resume", "resumir",
    "remova", "remover", "apague", "apagar", "exclua", "excluir",
)
# These requests need the capable/main agent when they are asking the routine to DO
# research/analysis, rather than merely reminding the user to do it.
_SMART_WORK_MARKERS = (
    "pesquise", "pesquisar", "procure", "procurar", "busque", "buscar",
    "internet", "web", "browser", "site", "noticia", "noticias",
    "vaga", "vagas", "empresa", "empresas", "oportunidade", "oportunidades",
    "analise", "analisar", "compare", "comparar", "resuma", "resumir",
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def _is_explicit_reminder(text: str) -> bool:
    folded = _fold(text)
    return any(marker in folded for marker in _CREATE_MARKERS)


def _is_management_candidate(text: str) -> bool:
    folded = _fold(text)
    return (
        any(word in folded for word in _ROUTINE_WORDS)
        and any(marker in folded for marker in _MANAGE_MARKERS)
    )


def _is_list_request(text: str) -> bool:
    folded = _fold(text)
    return (
        any(word in folded for word in _ROUTINE_WORDS)
        and any(marker in folded for marker in ("liste", "listar", "mostre", "mostrar", "quais"))
    )


def _needs_main_agent(text: str) -> bool:
    """True when a routine request itself asks Hermes to perform intelligent/dynamic work."""
    folded = _fold(text)
    if not any(marker in folded for marker in _SMART_WORK_MARKERS):
        return False
    # "me lembre de pesquisar vagas" is a static reminder.  "crie uma rotina que
    # pesquise vagas e me mande..." is autonomous work and belongs on MiMo.
    if _is_explicit_reminder(text):
        autonomous_shapes = (
            "rotina que ", "rotina para pesquisar", "rotina para buscar",
            "rotina para procurar", "todo dia pesquise", "todos os dias pesquise",
        )
        return any(shape in folded for shape in autonomous_shapes)
    return True


def is_fastpath_candidate(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    if _needs_main_agent(text):
        return False
    return _is_explicit_reminder(text) or _is_management_candidate(text)


def _config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        section = cfg.get("local_fastpath") or {}
        return section if isinstance(section, dict) else {}
    except Exception:
        logger.debug("local_fastpath: config unavailable", exc_info=True)
        return {}


def _ollama_endpoint(base_url: str) -> str:
    base = (base_url or "http://127.0.0.1:11434").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/api/chat"


def _parse_local_json(text: str, cfg: dict[str, Any], timezone_name: str) -> Optional[dict[str, Any]]:
    model = str(cfg.get("model") or "qwen3.5:2b-q4_K_M")
    base_url = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    timeout = float(cfg.get("timeout_seconds") or 15)
    now = datetime.now(ZoneInfo(timezone_name))
    system = f"""Você é o parser LOCAL de ações simples do Hermes. Responda SOMENTE um objeto JSON válido.
Agora: {now.isoformat()}
Fuso: {timezone_name}

Você NÃO conversa, NÃO pesquisa e NÃO inventa dados. Só converte pedidos explícitos de lembrete/rotina.
Se houver dúvida, condição externa, pesquisa, notícia, vaga, empresa, site, análise ou tarefa que o Hermes
precise executar no futuro, retorne {{"route":"main"}}.

Ações permitidas:
1) Criar lembrete/rotina estática:
{{"route":"local","action":"create","name":"título curto 2-5 palavras","schedule":"agenda Hermes","message":"texto curto a entregar"}}
2) Pausar/retomar/remover rotina pelo nome ou id:
{{"route":"local","action":"pause|resume|remove","job_ref":"nome ou id informado pelo usuário"}}
3) Listar:
{{"route":"local","action":"list"}}

Agenda aceita:
- data/hora específica -> ISO-8601, ex. 2026-09-19T10:00:00-03:00
- atraso -> "in 30m", "in 2h"
- recorrente -> "every 2h", "every day at 9am", "weekdays at 9am"
- janela -> "every 2h between 08:00 and 18:00 on weekdays"
- cron de 5 campos quando necessário.
Para datas relativas como amanhã, calcule usando a data/hora acima.
O campo message é apenas o lembrete a ser enviado, em português. Não inclua a agenda nele.
Nunca copie a instrução inteira como name.
"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text.strip()},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": -1,
        "options": {"num_ctx": 4096, "num_predict": 256, "temperature": 0},
    }
    request = urllib.request.Request(
        _ollama_endpoint(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        raw = ((body.get("message") or {}).get("content") or "").strip()
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        logger.warning("local_fastpath: local parser failed, falling back to main agent: %s", exc)
        return None


def _delivery_target(source: Any) -> str:
    platform = getattr(getattr(source, "platform", None), "value", None) or str(
        getattr(source, "platform", "")
    )
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    target = f"{platform}:{chat_id}"
    return f"{target}:{thread_id}" if thread_id else target


def _format_schedule(job: dict[str, Any]) -> str:
    return str(job.get("schedule") or job.get("schedule_display") or "").strip()


def _format_list() -> str:
    from cron.jobs import list_jobs

    jobs = list_jobs(include_disabled=True)
    if not jobs:
        return "Você não tem rotinas cadastradas."
    lines = ["Suas rotinas:"]
    for job in jobs[:30]:
        name = job.get("name") or job.get("id")
        state = job.get("state") or ("ativa" if job.get("enabled", True) else "pausada")
        schedule = job.get("schedule_display") or "sem agenda"
        lines.append(f"• {name} — {schedule} — {state}")
    if len(jobs) > 30:
        lines.append(f"• … e mais {len(jobs) - 30}")
    return "\n".join(lines)


def _handle_action(parsed: dict[str, Any], source: Any) -> Optional[str]:
    action = str(parsed.get("action") or "").strip().lower()
    if parsed.get("route") != "local":
        return None

    if action == "list":
        return _format_list()

    from tools.cronjob_tools import cronjob

    if action == "create":
        name = str(parsed.get("name") or "").strip()
        schedule = str(parsed.get("schedule") or "").strip()
        message = str(parsed.get("message") or "").strip()
        if not name or not schedule or not message:
            return None
        raw = cronjob(
            action="create",
            prompt=message,
            schedule=schedule,
            name=name,
            deliver=_delivery_target(source),
            no_agent=True,
        )
        result = json.loads(raw)
        if not result.get("success"):
            logger.info("local_fastpath: create rejected (%s); main agent will retry", result.get("error"))
            return None
        job = result.get("job") or {}
        return f"⏰ Rotina criada: {job.get('name') or name} — {job.get('schedule') or schedule}"

    if action not in {"pause", "resume", "remove"}:
        return None
    job_ref = str(parsed.get("job_ref") or "").strip()
    if not job_ref:
        return None
    raw = cronjob(action=action, job_id=job_ref)
    result = json.loads(raw)
    if not result.get("success"):
        # Ambiguous/missing references are safer on the capable agent, which can list and ask.
        logger.info("local_fastpath: %s rejected for %r; falling back to main", action, job_ref)
        return None
    if action == "remove":
        return f"🗑️ Rotina removida: {job_ref}"
    job = result.get("job") or {}
    label = job.get("name") or job_ref
    return f"⏸️ Rotina pausada: {label}" if action == "pause" else f"▶️ Rotina retomada: {label}"


async def try_handle_local_fastpath(event: Any, source: Any) -> Optional[str]:
    """Return a complete local response, or None to continue into the normal main-agent path."""
    cfg = _config()
    if not bool(cfg.get("enabled", False)):
        return None
    if getattr(event, "media_urls", None) or getattr(event, "media_types", None):
        return None
    if callable(getattr(event, "get_command", None)) and event.get_command():
        return None

    text = str(getattr(event, "text", "") or "").strip()
    if not is_fastpath_candidate(text):
        return None

    # Listing is deterministic and needs no model at all.
    if _is_list_request(text):
        try:
            return await asyncio.to_thread(_format_list)
        except Exception:
            logger.warning("local_fastpath: list failed; falling back to main", exc_info=True)
            return None

    try:
        from hermes_cli.config import load_config_readonly

        root_cfg = load_config_readonly() or {}
        timezone_name = str(root_cfg.get("timezone") or "America/Sao_Paulo")
    except Exception:
        timezone_name = "America/Sao_Paulo"

    parsed = await asyncio.to_thread(_parse_local_json, text, cfg, timezone_name)
    if not parsed:
        return None
    try:
        return await asyncio.to_thread(_handle_action, parsed, source)
    except Exception:
        logger.warning("local_fastpath: action failed; falling back to main", exc_info=True)
        return None
