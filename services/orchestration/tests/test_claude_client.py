import os
from types import SimpleNamespace

import pytest

from app.engine.claude_client import ClaudeClient


class DummyMessagesClient:
    def __init__(self):
        self.last_args = None
        self.last_kwargs = None

    def create(self, *args, **kwargs):
        self.last_args = args
        self.last_kwargs = kwargs
        # Minimal object with the shape used in ClaudeClient.send
        return SimpleNamespace(
            content=[SimpleNamespace(text="dummy-response")]
        )


class DummyAnthropicClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.messages = DummyMessagesClient()


def test_claude_client_requires_api_key(monkeypatch):
    # Ensure env var is not set
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError) as excinfo:
        ClaudeClient()

    assert "ANTHROPIC_API_KEY not set" in str(excinfo.value)


def test_claude_client_uses_env_api_key(monkeypatch):
    # Patch Anthropic to our dummy client
    from app import engine as engine_pkg  # type: ignore[import]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

    # Monkeypatch the Anthropic class in the claude_client module
    import app.engine.claude_client as cc

    monkeypatch.setattr(cc, "Anthropic", DummyAnthropicClient)

    client = cc.ClaudeClient()
    assert isinstance(client.client, DummyAnthropicClient)
    assert client.client.api_key == "env-key"


def test_claude_client_send_returns_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

    import app.engine.claude_client as cc

    monkeypatch.setattr(cc, "Anthropic", DummyAnthropicClient)

    client = cc.ClaudeClient(model="claude-sonnet-4-6")
    resp_text = client.send("Hello, Claude", system_prompt="You are a test.")

    assert resp_text == "dummy-response"
    # Verify that the underlying client was called with expected params
    msgs = client.client.messages
    assert msgs.last_kwargs["model"] == "claude-sonnet-4-6"
    assert msgs.last_kwargs["max_tokens"] == 2048
    assert msgs.last_kwargs["system"] == "You are a test."
    assert msgs.last_kwargs["messages"] == [{"role": "user", "content": "Hello, Claude"}]

