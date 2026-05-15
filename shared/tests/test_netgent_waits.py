import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.subagents.browser.generate.generate import (
    _convert_action,
)
from registry.actions import playwright as playwright_actions
from registry.actions.base import ActionContext


def test_convert_action_preserves_string_wait_seconds() -> None:
    workflow_action = _convert_action(
        {
            "type": "wait",
            "params": {"seconds": "30"},
        }
    )

    assert workflow_action is not None
    assert workflow_action.type == "wait"
    assert workflow_action.params == {"seconds": 30}


def test_playwright_wait_reports_actual_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[int] = []

    async def fake_sleep(seconds: int) -> None:
        slept.append(seconds)

    monkeypatch.setattr(playwright_actions, "_resolve_page", lambda ctx: object())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    result = asyncio.run(playwright_actions.wait(seconds="30", ctx=ActionContext()))

    assert slept == [30]
    assert result["seconds"] == "30"
    assert result["slept_seconds"] == "30"
    assert result["message"] == "Waiting for 30 seconds"
