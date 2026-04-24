import pytest

from app.agent import utils


def test_get_model_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ORCHESTRATION_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    captured = {}

    class DummyAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(utils, "ChatAnthropic", DummyAnthropic)

    model = utils.get_model()

    assert isinstance(model, DummyAnthropic)
    assert captured["model_name"] == "claude-sonnet-4-6"
    assert captured["api_key"].get_secret_value() == "anthropic-key"


def test_get_model_uses_gemini_when_configured(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    captured = {}

    class DummyGoogle:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(utils, "ChatGoogleGenerativeAI", DummyGoogle)

    model = utils.get_model()

    assert isinstance(model, DummyGoogle)
    assert captured["model"] == "gemini-3.1-flash-lite-preview"
    assert captured["google_api_key"].get_secret_value() == "google-key"


def test_get_model_rejects_invalid_provider(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_PROVIDER", "openai")

    with pytest.raises(ValueError):
        utils.get_model_provider()


def test_with_structured_output_uses_json_mode_for_gemini(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_PROVIDER", "gemini")

    calls = {}

    class DummyModel:
        def with_structured_output(self, schema, **kwargs):
            calls["schema"] = schema
            calls["kwargs"] = kwargs
            return "structured"

    result = utils.with_structured_output(DummyModel(), object, include_raw=True)

    assert result == "structured"
    assert calls["schema"] is object
    assert calls["kwargs"]["method"] == "json_mode"
    assert calls["kwargs"]["include_raw"] is True
