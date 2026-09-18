"""Plain-language copy for the one-line cron failure notice delivered to a job's chat.

The scheduler classifies the failure text through ``agent.error_classifier.classify_api_error``
(one classifier for the whole app, no cron-local regex ladder) and looks the verdict up here.
Every notice says WHAT happened and WHAT TO DO, and names the exact ``hermes cron`` command plus
the real output directory — "cron output" alone sent operators hunting.
"""

from __future__ import annotations

import re
from typing import Optional

from hermes_constants import display_hermes_home


def cron_output_dir_display(job_id: str) -> str:
    """User-facing path of a job's saved run output (profile-aware)."""
    return f"{display_hermes_home()}/cron/output/{job_id}/"


_HTTP_STATUS_IN_TEXT = re.compile(r"(?:\bHTTP\b|\bError code\b|\bstatus(?: code)?\b)\W{0,3}(\b[45]\d\d\b)", re.I)
_LEADING_EXC_TYPE = re.compile(r"^(?:[\w.]+\.)?([A-Z]\w*(?:Error|Timeout|Exception))\s*:")


def classify_cron_failure_reason(text: str) -> str:
    """``FailoverReason`` value for a cron failure string (``"unknown"`` when unclassifiable).

    The scheduler only has ``str(exc)``, so the status code and exception type the classifier
    keys on are rebuilt from the text: a whole-token HTTP code after ``HTTP`` / ``Error code`` /
    ``status`` (a bare ``429`` inside a job id or hash never counts, #83188) and a leading
    ``ReadTimeout:``-style type prefix."""
    from agent.error_classifier import classify_api_error

    status = _HTTP_STATUS_IN_TEXT.search(text)
    type_name = _LEADING_EXC_TYPE.match(text)
    exc_cls = type(type_name.group(1), (Exception,), {}) if type_name else Exception
    exc = exc_cls(text)
    if status:
        exc.status_code = int(status.group(1))
    return classify_api_error(exc).reason.value


# What happened, per reason: the one gloss table shared with subagent notices lives in
# agent/turn_failure_copy.py so the two never drift; the job is the subject here.
_PROVIDER_FAILURE_CAUSE_PT: dict[str, str] = {
    "timeout": "o serviço do modelo de IA não respondeu a tempo",
    "rate_limit": "o serviço do modelo de IA atingiu o limite de requisições",
    "upstream_rate_limit": "o serviço do modelo de IA atingiu o limite de requisições",
    "overloaded": "o serviço do modelo de IA está sobrecarregado no momento",
    "server_error": "o serviço do modelo de IA retornou um erro interno",
    "billing": "a conta atingiu o limite de uso ou de créditos",
    "billing_unverified": "a conta atingiu o limite de uso ou de créditos",
    "auth": "o serviço do modelo de IA recusou a autenticação",
    "auth_permanent": "o serviço do modelo de IA recusou a autenticação",
    "model_not_found": "o modelo usado por esta rotina não foi encontrado",
    "content_policy_blocked": "o filtro de segurança do serviço recusou a solicitação",
    "context_overflow": "a solicitação desta rotina ficou grande demais para o modelo",
    "payload_too_large": "a solicitação desta rotina ficou grande demais para o modelo",
}


def _provider_failure_cause(reason: str) -> Optional[str]:
    """Descrição em pt-BR para uma falha classificada do provedor."""
    return _PROVIDER_FAILURE_CAUSE_PT.get(reason)


_TRANSIENT_REASONS = frozenset({"timeout", "rate_limit", "upstream_rate_limit", "overloaded", "server_error"})

# Reason -> what to do. Transient reasons get the backup-provider clause from the scheduler
# (it knows whether a fallback chain is configured) instead of a fixed sentence.
_PROVIDER_FAILURE_ACTION: dict[str, str] = {
    "billing": (
        "Adicione créditos ou aguarde a renovação do limite, ou fixe outro provedor com "
        "`hermes cron edit {job_id} --provider <name>`."
    ),
    "auth": (
        "Autentique-se novamente com /login (ou `hermes auth add <provider>` no terminal), ou fixe um "
        "provedor funcional com `hermes cron edit {job_id} --provider <name>` e depois use "
        "`hermes cron run {job_id}` para tentar novamente."
    ),
    "model_not_found": "Escolha outro modelo com `hermes cron edit {job_id} --model <name>`.",
    "context_overflow": "Reduza o prompt da rotina com `hermes cron edit {job_id} --prompt <text>`.",
}
_PROVIDER_FAILURE_ACTION["auth_permanent"] = _PROVIDER_FAILURE_ACTION["auth"]
_PROVIDER_FAILURE_ACTION["billing_unverified"] = _PROVIDER_FAILURE_ACTION["billing"]
_PROVIDER_FAILURE_ACTION["payload_too_large"] = _PROVIDER_FAILURE_ACTION["context_overflow"]
_PROVIDER_FAILURE_ACTION["content_policy_blocked"] = (
    "Reescreva o prompt da rotina com `hermes cron edit {job_id} --prompt <text>`, ou escolha outro "
    "modelo com `hermes cron edit {job_id} --model <name>`."
)
_DEFAULT_FAILURE_ACTION = "Execute novamente com `hermes cron run {job_id}` ou edite com `hermes cron edit {job_id}`."


def provider_failure_notice(
    job_name: str, job_id: str, reason: str, *, backup_provider_phrase: str,
) -> Optional[str]:
    """The notice for a provider-shaped ``reason``, or None when the reason is not one."""
    cause = _provider_failure_cause(reason)
    if cause is None:
        return None
    if reason in _TRANSIENT_REASONS:
        action = (
            f"{backup_provider_phrase} Ela tentará novamente no próximo horário programado; "
            f"`hermes cron run {job_id}` tenta agora."
        )
    else:
        action = _PROVIDER_FAILURE_ACTION.get(reason, _DEFAULT_FAILURE_ACTION).format(job_id=job_id)
    return (
        f"⚠️ Rotina '{job_name}' falhou: {cause}. {action} "
        f"Histórico: `hermes cron runs {job_id}`."
    )


def generic_failure_notice(job_name: str, job_id: str, cleaned_error: str) -> str:
    """Unclassified failure: the cleaned error text plus where to look and what to do."""
    return (
        f"⚠️ Rotina '{job_name}' falhou: {cleaned_error}. "
        f"Veja a execução completa com `hermes cron runs {job_id}` (saída salva em "
        f"{cron_output_dir_display(job_id)}); execute novamente com `hermes cron run {job_id}`, "
        f"edite com `hermes cron edit {job_id}` ou pause com `hermes cron pause {job_id}`."
    )


def script_timeout_notice(job_name: str, job_id: str) -> str:
    return (
        f"⚠️ Rotina '{job_name}' falhou: o script excedeu o tempo limite. Nenhum modelo foi chamado. "
        f"Confira a saída do script em {cron_output_dir_display(job_id)} ou em `hermes cron runs {job_id}`, "
        f"depois execute novamente com `hermes cron run {job_id}`."
    )


def inactivity_notice(job_name: str, job_id: str) -> str:
    return (
        f"⚠️ Rotina '{job_name}' falhou: a execução travou e ficou tempo demais sem atividade "
        f"e foi interrompida. Veja o que estava acontecendo na saída salva em "
        f"{cron_output_dir_display(job_id)} (`hermes cron runs {job_id}`) e depois execute novamente com "
        f"`hermes cron run {job_id}`."
    )


def blocked_config_notice(job_name: str, reason: str) -> str:
    """One-time notice when the pre-run configuration check refused to start the job."""
    reason = reason.rstrip()
    if reason and reason[-1] not in ".!?":
        reason += "."
    return (
        f"⛔ Rotina '{job_name}' não executou: {reason} Nada foi cobrado. O Hermes tentará novamente no "
        "próximo horário programado e não repetirá este alerta; verifique com "
        "`hermes cron doctor`."
    )
