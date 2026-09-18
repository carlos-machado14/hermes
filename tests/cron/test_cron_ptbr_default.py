import cron.scheduler_prompt as scheduler_prompt


def test_cron_hint_defaults_to_brazilian_portuguese():
    hint = scheduler_prompt._CRON_HINT
    assert "Brazilian Portuguese (pt-BR)" in hint
    assert "Only use another language" in hint
    assert "[SILENT]" in hint
