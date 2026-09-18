from datetime import datetime, timezone

import pytest

import cron.jobs as jobs


def _freeze(monkeypatch, value: datetime) -> None:
    monkeypatch.setattr(jobs, "_hermes_now", lambda: value)
    monkeypatch.setattr(jobs, "get_timezone", lambda: timezone.utc)


def test_parse_bounded_interval_weekdays():
    schedule = jobs.parse_schedule(
        "every 2h between 08:00 and 18:00 on weekdays"
    )

    assert schedule == {
        "kind": "bounded_interval",
        "minutes": 120,
        "start_time": "08:00",
        "end_time": "18:00",
        "weekdays": [0, 1, 2, 3, 4],
        "display": "every 120m, 08:00-18:00, weekdays",
    }


def test_parse_bounded_interval_selected_days():
    schedule = jobs.parse_schedule(
        "every 30m between 09:00 and 17:00 on monday,wednesday,friday"
    )

    assert schedule["kind"] == "bounded_interval"
    assert schedule["minutes"] == 30
    assert schedule["weekdays"] == [0, 2, 4]


def test_bounded_interval_next_run_is_anchored_to_window_start(monkeypatch):
    # Monday 2026-09-21 09:15 UTC -> 08:00, 10:00, 12:00... lattice.
    now = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
    _freeze(monkeypatch, now)
    schedule = jobs.parse_schedule(
        "every 2h between 08:00 and 18:00 on weekdays"
    )

    assert jobs.compute_next_run(schedule) == "2026-09-21T10:00:00+00:00"


def test_bounded_interval_skips_disallowed_days(monkeypatch):
    # Friday after the final slot -> next Monday at the window start.
    now = datetime(2026, 9, 25, 18, 30, tzinfo=timezone.utc)
    _freeze(monkeypatch, now)
    schedule = jobs.parse_schedule(
        "every 2h between 08:00 and 18:00 on weekdays"
    )

    assert jobs.compute_next_run(schedule) == "2026-09-28T08:00:00+00:00"


def test_bounded_interval_rejects_overnight_window():
    with pytest.raises(ValueError, match="cannot cross midnight"):
        jobs.parse_schedule(
            "every 2h between 22:00 and 06:00 on weekdays"
        )


def test_full_prompt_is_not_used_as_cron_title(monkeypatch, tmp_path):
    now = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)
    _freeze(monkeypatch, now)
    monkeypatch.setattr(
        jobs,
        "_compute_provider_model_snapshots",
        lambda **kwargs: (None, None),
    )

    prompt = "Me lembre de beber água a cada 2 horas das 08:00 às 18:00"

    with jobs.use_cron_store(tmp_path):
        job = jobs.create_job(
            prompt=prompt,
            schedule="every 2h between 08:00 and 18:00 on weekdays",
            name=prompt,
        )

    assert job["name"] == "beber água"
    assert job["name"] != prompt
