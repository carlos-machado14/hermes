"""Small fail-open client for Jev through OpenCode Zen System One.

Jev is not a chat model and does not replace MiMo. It is a cheap, low-latency typed
classifier for routing/scoring/guardrails inside Hermes workflows. The client is optional:
when disabled, unconfigured, unavailable, or uncertain it returns ``None`` and callers keep
the existing Hermes behavior.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def _config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
        section = cfg.get("jev") or {}
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def enabled() -> bool:
    cfg = _config()
    value = cfg.get("enabled", False)
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def decide(
    state: Any,
    questions: Mapping[str, Mapping[str, Any]],
    *,
    min_confidence: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate typed System One questions with Jev through OpenCode Zen.

    Returns the OpenCode response dictionary, or ``None`` on configuration/network/API
    failure. Choice/score answers below ``min_confidence`` also fail open. Noul answers
    expose a probability rather than a separate confidence and are left to the caller's
    threshold policy.
    """
    cfg = _config()
    if not enabled():
        return None

    api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if not api_key:
        logger.warning("Jev enabled but OPENCODE_API_KEY is missing; falling back")
        return None

    base_url = str(cfg.get("base_url") or "https://opencode.ai/zen/v1").rstrip("/")
    model = str(cfg.get("model") or "jev-1.13-free")
    timeout = float(cfg.get("timeout_seconds") or 5)
    threshold = float(min_confidence if min_confidence is not None else cfg.get("min_confidence", 0.80))
    payload = {"state": state, "model": model, "questions": dict(questions)}
    request = urllib.request.Request(
        f"{base_url}/systemone",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        answers = result.get("answers")
        if not isinstance(answers, dict):
            return None
        for answer in answers.values():
            if not isinstance(answer, dict):
                return None
            if answer.get("type") in {"choice", "score"}:
                confidence = answer.get("confidence")
                if not isinstance(confidence, (int, float)) or float(confidence) < threshold:
                    logger.info("Jev decision below confidence threshold %.2f; falling back", threshold)
                    return None
        return result
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        logger.warning("OpenCode Jev request failed; falling back to existing Hermes path: %s", exc)
        return None


def choose(state: Any, instructions: str, criteria: Mapping[str, Any]) -> Optional[str]:
    """Convenience choice decision; returns the selected key or ``None`` fail-open."""
    result = decide(
        state,
        {"decision": {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}},
    )
    if not result:
        return None
    answer = (result.get("answers") or {}).get("decision") or {}
    choice = answer.get("choice")
    return str(choice) if choice is not None else None
