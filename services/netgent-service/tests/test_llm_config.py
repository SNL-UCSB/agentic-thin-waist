import pytest
import sys
from types import SimpleNamespace

from clients.netgent.src.agent import model_factory


def test_netgent_langchain_model_uses_gemini(monkeypatch):
    monkeypatch.setenv("NETGENT_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    captured = {}

    class DummyGoogle:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(model_factory, "ChatGoogleGenerativeAI", DummyGoogle)

    model = model_factory.get_langchain_model()

    assert isinstance(model, DummyGoogle)
    assert captured["model"] == "gemini-3.1-flash-lite-preview"
    assert captured["google_api_key"].get_secret_value() == "google-key"


def test_netgent_langchain_model_uses_anthropic(monkeypatch):
    monkeypatch.setenv("NETGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    captured = {}

    class DummyAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(model_factory, "LangChainChatAnthropic", DummyAnthropic)

    model = model_factory.get_langchain_model()

    assert isinstance(model, DummyAnthropic)
    assert captured["model_name"] == "claude-sonnet-4-6"
    assert captured["api_key"].get_secret_value() == "anthropic-key"


def test_netgent_browser_use_model_uses_anthropic(monkeypatch):
    monkeypatch.setenv("NETGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CLAUDE_API_KEY", "claude-key")

    captured = {}

    class DummyBrowserAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class DummyBrowserGoogle:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setitem(
        sys.modules,
        "browser_use",
        SimpleNamespace(
            ChatAnthropic=DummyBrowserAnthropic,
            ChatGoogle=DummyBrowserGoogle,
        ),
    )

    model = model_factory.get_browser_use_model()

    assert isinstance(model, DummyBrowserAnthropic)
    assert captured["model"] == "claude-sonnet-4-6"


def test_netgent_provider_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("NETGENT_LLM_PROVIDER", "openai")

    with pytest.raises(ValueError):
        model_factory.get_llm_provider()
