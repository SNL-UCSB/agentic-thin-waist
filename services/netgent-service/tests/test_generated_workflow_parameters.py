from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from netgent.src.agent.subagents.browser import agent as browser_agent_module
from netgent.src.agent.subagents.browser.generate import (
    agent as browser_generate_agent_module,
)
from netgent.src.agent.subagents.shell import agent as shell_agent_module


def test_shell_generation_uses_parameter_name_list():
    state = {
        "task": "Ping the target host",
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "RunPingTool",
                        "args": {
                            "host": "1.1.1.1",
                            "count": 3,
                            "reasoning": "measure reachability",
                        },
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        ],
        "parameters": {
            "host": "1.1.1.1",
            "count": "3",
        },
    }

    response = shell_agent_module.generate_workflow(state)
    workflow = response["workflow"]

    assert workflow["parameters"] == ["host", "count"]
    assert workflow["states"][0]["actions"] == [
        {
            "type": "ping",
            "params": {
                "host": "{{host}}",
                "count": "{{count}}",
            },
        }
    ]


def test_browser_generation_uses_parameter_name_list(monkeypatch):
    class FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    class FakePlaywrightLauncher:
        def __init__(self, playwright: FakePlaywright) -> None:
            self.playwright = playwright

        async def start(self) -> FakePlaywright:
            return self.playwright

    class FakeGenerateAgent:
        async def ainvoke(self, payload, context):
            assert payload["parameters"] == {
                "url": "https://example.com",
                "wait_seconds": "5",
            }
            assert context["playwright"] is fake_playwright
            return {
                "result": {
                    "success": True,
                    "message": "Workflow Generated!",
                },
                "workflow": {
                    "specification": payload["task"],
                    "states": [
                        {
                            "checks": [{"type": "always_true", "params": {}}],
                            "actions": [
                                {
                                    "type": "go_to_url",
                                    "params": {
                                        "url": "<secret>url</secret>",
                                        "new_tab": False,
                                    },
                                },
                                {
                                    "type": "wait",
                                    "params": {
                                        "seconds": "<secret>wait_seconds</secret>"
                                    },
                                },
                            ],
                            "end_state": "Workflow Completed",
                        }
                    ],
                },
            }

    fake_playwright = FakePlaywright()
    monkeypatch.setattr(
        browser_agent_module,
        "async_playwright",
        lambda: FakePlaywrightLauncher(fake_playwright),
    )
    monkeypatch.setattr(
        browser_agent_module,
        "create_browser_generate_agent",
        lambda: FakeGenerateAgent(),
    )

    response = asyncio.run(
        browser_agent_module.generate_workflow(
            {
                "task": "Open a page and wait",
                "messages": [],
                "parameters": {
                    "url": "https://example.com",
                    "wait_seconds": "5",
                },
            }
        )
    )
    workflow = response["workflow"]

    assert fake_playwright.stopped is True
    assert workflow["parameters"] == ["url", "wait_seconds"]
    assert workflow["states"][0]["actions"] == [
        {
            "type": "go_to_url",
            "params": {
                "url": "{{url}}",
                "new_tab": False,
            },
        },
        {
            "type": "wait",
            "params": {"seconds": "{{wait_seconds}}"},
        },
    ]


def test_browser_generate_execute_task_uses_sensitive_data(monkeypatch):
    captured: dict[str, object] = {}

    class FakeBrowserInstance:
        async def close(self) -> None:
            captured["browser_closed"] = True

    class FakeBrowserWrapper:
        def __init__(self, **kwargs) -> None:
            captured["browser_kwargs"] = kwargs

    class FakeHistory:
        def model_dump(self) -> dict[str, list[dict[str, object]]]:
            return {"history": []}

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            captured["agent_kwargs"] = kwargs

        async def run(self, max_steps: int) -> FakeHistory:
            captured["max_steps"] = max_steps
            return FakeHistory()

    async def fake_open_browser_session(playwright):
        captured["playwright"] = playwright
        return FakeBrowserInstance(), object(), None

    monkeypatch.setattr(browser_generate_agent_module, "Browser", FakeBrowserWrapper)
    monkeypatch.setattr(browser_generate_agent_module, "Agent", FakeAgent)
    monkeypatch.setattr(
        browser_generate_agent_module,
        "open_browser_session",
        fake_open_browser_session,
    )
    monkeypatch.setattr(
        browser_generate_agent_module,
        "build_controller",
        lambda excluded_actions: excluded_actions,
    )
    monkeypatch.setattr(
        browser_generate_agent_module,
        "coerce_evolution",
        lambda task, evolution: evolution,
    )
    monkeypatch.setattr(
        browser_generate_agent_module,
        "build_evolutionary_prompt",
        lambda task, evolution: task,
    )
    monkeypatch.setattr(
        browser_generate_agent_module,
        "update_evolution",
        lambda task, history, evolution: evolution,
    )

    result = asyncio.run(
        browser_generate_agent_module.execute_task(
            {
                "task": "Open the provided URL and wait for the provided time.",
                "messages": [],
                "parameters": {
                    "url": "https://example.com",
                    "wait_seconds": "5",
                },
            },
            SimpleNamespace(context=SimpleNamespace(playwright="fake-playwright")),
        )
    )

    agent_kwargs = captured["agent_kwargs"]
    assert isinstance(agent_kwargs, dict)
    assert agent_kwargs["sensitive_data"] == {
        "url": "https://example.com",
        "wait_seconds": "5",
    }
    assert "<secret>url</secret>" in agent_kwargs["task"]
    assert "<secret>wait_seconds</secret>" in agent_kwargs["task"]
    assert "https://example.com" not in agent_kwargs["task"]
    assert result["history"]
    assert captured["browser_closed"] is True


def test_browser_generation_infers_wait_parameter_placeholder(monkeypatch):
    class FakePlaywright:
        async def stop(self) -> None:
            return None

    class FakePlaywrightLauncher:
        async def start(self) -> FakePlaywright:
            return FakePlaywright()

    class FakeGenerateAgent:
        async def ainvoke(self, payload, context):
            return {
                "result": {
                    "success": True,
                    "message": "Workflow Generated!",
                },
                "workflow": {
                    "specification": payload["task"],
                    "states": [
                        {
                            "checks": [{"type": "always_true", "params": {}}],
                            "actions": [
                                {
                                    "type": "go_to_url",
                                    "params": {
                                        "url": "https://www.youtube.com/watch?v=5cZ6h_koun0",
                                        "new_tab": False,
                                    },
                                },
                                {
                                    "type": "wait",
                                    "params": {"seconds": 3},
                                },
                            ],
                            "end_state": "Workflow Completed",
                        }
                    ],
                },
            }

    monkeypatch.setattr(
        browser_agent_module,
        "async_playwright",
        lambda: FakePlaywrightLauncher(),
    )
    monkeypatch.setattr(
        browser_agent_module,
        "create_browser_generate_agent",
        lambda: FakeGenerateAgent(),
    )

    response = asyncio.run(
        browser_agent_module.generate_workflow(
            {
                "task": "Open the provided YouTube link and wait for the provided watch time.",
                "messages": [],
                "parameters": {
                    "yt_link": "https://www.youtube.com/watch?v=5cZ6h_koun0",
                    "wait_watch_time": "30",
                },
            }
        )
    )
    workflow = response["workflow"]

    assert workflow["parameters"] == ["yt_link", "wait_watch_time"]
    assert workflow["states"][0]["actions"] == [
        {
            "type": "go_to_url",
            "params": {
                "url": "{{yt_link}}",
                "new_tab": False,
            },
        },
        {
            "type": "wait",
            "params": {"seconds": "{{wait_watch_time}}"},
        },
    ]
