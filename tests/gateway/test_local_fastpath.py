"""Tests for the V1 hybrid local reminder fast-path."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gateway import local_fastpath as lf


def test_normal_conversation_never_wakes_local_model():
    assert lf.is_fastpath_candidate("Qual é a capital do Brasil?") is False
    assert lf.is_fastpath_candidate("Explique Riverpod para mim") is False


def test_explicit_reminder_is_local_candidate():
    assert lf.is_fastpath_candidate("Me lembre amanhã às 10h de revisar minhas tarefas") is True
    assert lf.is_fastpath_candidate("Me cobre a cada 2 horas para beber água") is True


def test_autonomous_research_routine_stays_on_main_agent():
    assert lf.is_fastpath_candidate(
        "Crie uma rotina que pesquise vagas Flutter todos os dias e me mande as melhores"
    ) is False


def test_static_reminder_about_research_can_stay_local():
    assert lf.is_fastpath_candidate(
        "Me lembre amanhã às 10h de pesquisar vagas Flutter"
    ) is True


def test_list_request_does_not_need_local_llm():
    assert lf._is_list_request("Quais são minhas rotinas?") is True


def test_create_action_uses_static_no_agent_cron(monkeypatch):
    calls = {}

    def fake_cronjob(**kwargs):
        calls.update(kwargs)
        return json.dumps({
            "success": True,
            "job": {"name": "Beber água", "schedule": "every 2h"},
        })

    import tools.cronjob_tools as cron_tools

    monkeypatch.setattr(cron_tools, "cronjob", fake_cronjob)
    source = SimpleNamespace(
        platform=SimpleNamespace(value="telegram"),
        chat_id="123",
        thread_id="45",
    )
    response = lf._handle_action({
        "route": "local",
        "action": "create",
        "name": "Beber água",
        "schedule": "every 2h",
        "message": "Lembrete: beber água.",
    }, source)

    assert calls["no_agent"] is True
    assert calls["prompt"] == "Lembrete: beber água."
    assert calls["deliver"] == "telegram:123:45"
    assert response == "⏰ Rotina criada: Beber água — every 2h"


@pytest.mark.asyncio
async def test_local_parser_failure_falls_through_to_main(monkeypatch):
    monkeypatch.setattr(lf, "_config", lambda: {"enabled": True})
    monkeypatch.setattr(lf, "_parse_local_json", lambda *_args: None)

    event = SimpleNamespace(
        text="Me lembre amanhã às 10h de estudar",
        media_urls=[],
        media_types=[],
        get_command=lambda: None,
    )
    source = SimpleNamespace(platform=SimpleNamespace(value="telegram"), chat_id="123", thread_id=None)

    assert await lf.try_handle_local_fastpath(event, source) is None
