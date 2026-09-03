"""The AI seam: one result type, one error protocol, fallback on the value."""

from unittest.mock import patch

import pytest

from linkedin.ai.client import DEFAULT_MODEL, AIClientError, AIResult, ai_call


@patch("linkedin.ai.client.generate_with_ai", return_value="model text")
def test_ai_call_returns_model_text(mock_ai):
    result = ai_call("prompt", max_tokens=50)
    assert result == AIResult(text="model text")
    assert result.ok and result.source == "ai"
    mock_ai.assert_called_once_with("prompt", max_tokens=50)


@patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("down"))
def test_ai_call_without_fallback_returns_error_not_raise(mock_ai):
    result = ai_call("prompt")
    assert not result
    assert result.error == "down"
    assert result.was_fallback is False


@patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("down"))
def test_ai_call_with_fallback_keeps_the_error(mock_ai, monkeypatch):
    monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "1")
    result = ai_call("prompt", fallback="template text")
    assert result.text == "template text"
    assert result.was_fallback is True
    assert result.ok is False
    assert result.source == "template"
    assert result.error == "down"


@patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("down"))
def test_ai_call_fallback_can_be_switched_off(mock_ai, monkeypatch):
    monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "0")
    result = ai_call("prompt", fallback="template text")
    assert not result
    assert result.error == "down"


def test_ai_result_is_frozen():
    with pytest.raises(Exception):
        AIResult(text="x").text = "y"  # type: ignore[misc]


@pytest.mark.parametrize("env, expected", [("", DEFAULT_MODEL), ("claude-sonnet-5", "claude-sonnet-5")])
def test_model_comes_from_env_with_a_default(monkeypatch, env, expected):
    from linkedin.ai.client import generate_with_ai

    monkeypatch.setenv("LINKEDIN_AI_MODEL", env)
    with patch("anthropic.Anthropic") as client_cls:
        message = client_cls.return_value.messages.create.return_value
        message.content = [type("Block", (), {"text": "ok"})()]
        assert generate_with_ai("p", retries=0) == "ok"
        assert client_cls.return_value.messages.create.call_args.kwargs["model"] == expected
