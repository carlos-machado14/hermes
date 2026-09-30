from unittest.mock import patch

from gateway import jev_client


def test_jev_disabled_fails_open():
    with patch.object(jev_client, "_config", return_value={"enabled": False}):
        assert jev_client.decide("hello", {"x": {"type": "noul"}}) is None


def test_jev_missing_key_fails_open(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with patch.object(jev_client, "_config", return_value={"enabled": True}):
        assert jev_client.decide("hello", {"x": {"type": "noul"}}) is None


def test_choose_returns_none_when_decision_unavailable():
    with patch.object(jev_client, "decide", return_value=None):
        assert jev_client.choose("hello", "route", {"simple": None, "main": None}) is None


def test_choose_returns_selected_choice():
    response = {
        "model": "jev-latest",
        "answers": {
            "decision": {
                "type": "choice",
                "choice": "simple",
                "confidence": 0.94,
                "probabilities": {"simple": 0.94, "main": 0.06},
            }
        },
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    with patch.object(jev_client, "decide", return_value=response):
        assert jev_client.choose("hello", "route", {"simple": None, "main": None}) == "simple"
