from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from browser_use import AgentHistoryList, Controller
from browser_use.agent.views import ActionResult
from dotenv import load_dotenv
from playwright.async_api import Playwright

load_dotenv()


def _is_headless() -> bool:
    return os.getenv("BROWSER_USE_HEADLESS", "true").lower() == "true"


IGNORED_ACTIONS = {
    "done",
    "extract_page_content",
    "get_dropdown_options",
    "read_file",
    "replace_file_str",
    "write_file",
}


def _coerce_history_items(
    history: AgentHistoryList | str | dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(history, AgentHistoryList):
        history = history.model_dump()

    elif hasattr(history, "model_dump") and callable(history.model_dump):
        history = history.model_dump()

    if isinstance(history, str):
        history = json.loads(history)

    if isinstance(history, list):
        return history

    if isinstance(history, dict):
        items = history.get("history")
        if isinstance(items, list):
            return items

    raise ValueError(
        "history must be a list of steps or a dict containing a 'history' list"
    )


def _parse_action(action: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    if not isinstance(action, dict):
        return None, {}

    for action_type, params in action.items():
        if action_type in IGNORED_ACTIONS:
            return None, {}
        if isinstance(params, dict):
            return action_type, params
        return action_type, {}

    return None, {}


def parse_agent_history(
    history: AgentHistoryList | str | dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parsed_history: list[dict[str, Any]] = []

    for step in _coerce_history_items(history):
        model_output = step.get("model_output") or {}
        state = step.get("state") or {}

        actions = model_output.get("action") or []
        interacted_elements = state.get("interacted_element") or []

        parsed_actions = []
        for index, action in enumerate(actions):
            action_type, params = _parse_action(action)
            if action_type is None:
                continue

            interacted_element = None
            if index < len(interacted_elements):
                interacted_element = interacted_elements[index]

            parsed_actions.append(
                {
                    "type": action_type,
                    "params": params,
                    "interacted_element": interacted_element,
                }
            )

        parsed_history.append(
            {
                "next_goal": model_output.get("next_goal"),
                "thinking": model_output.get("thinking"),
                "state": state,
                "actions": parsed_actions,
            }
        )

    return parsed_history


def _count_relevant_actions(history: AgentHistoryList) -> int:
    action_count = 0

    for step in _coerce_history_items(history.model_dump()):
        model_output = step.get("model_output") or {}
        actions = model_output.get("action") or []
        for action in actions:
            action_type, _ = _parse_action(action)
            if action_type is not None:
                action_count += 1

    return action_count


def _is_failed_history(history: AgentHistoryList) -> bool:
    return history.is_successful() is False or history.has_errors()


def prune_agenthistorylist(
    history_list: list[AgentHistoryList], top_k: int = 5
) -> list[AgentHistoryList]:
    failed_histories: list[AgentHistoryList] = []
    successful_histories: list[AgentHistoryList] = []

    for history in history_list:
        if _is_failed_history(history):
            failed_histories.append(history)
        else:
            successful_histories.append(history)

    failed_histories.sort(key=_count_relevant_actions)
    successful_histories.sort(key=_count_relevant_actions)

    pruned_histories = list(failed_histories)
    for history in successful_histories:
        if len(pruned_histories) >= len(failed_histories) + max(0, top_k):
            break
        pruned_histories.append(history)

    return pruned_histories


def build_controller(exclude_actions: list[str] | None = None) -> Controller:
    # Ensure "wait" is NOT in exclude_actions — we overwrite it below.
    # The Registry checks exclude_actions on every @action call, so including
    # "wait" would block our custom registration too.
    excluded = [a for a in (exclude_actions or []) if a != "wait"]

    controller = Controller(exclude_actions=excluded)

    @controller.registry.action(
        "Wait for x seconds (minimum 1 second actual sleep). "
        "Use this to pause before the next action when a page needs time to load or animate. "
        "Reduces wait by 3 seconds to account for LLM overhead, but always sleeps at least 1 second. "
        "Accepts a sensitive_data placeholder (e.g. x_wait) in place of a literal number."
    )
    async def wait(seconds: str = "3") -> ActionResult:
        try:
            seconds_int = int(seconds)
        except (ValueError, TypeError):
            seconds_int = 3
        actual_seconds = max(seconds_int - 3, 1)
        msg = f"Waiting for {actual_seconds + 3} seconds"
        await asyncio.sleep(actual_seconds)
        return ActionResult(extracted_content=msg)

    return controller


def get_browserless_ws_endpoint() -> str | None:
    endpoint = os.getenv("BROWSERLESS_WS_ENDPOINT", "").strip()
    return endpoint or None


async def open_browser_session(
    playwright: Playwright, *, record_har_path: str | None = None
):
    endpoint = get_browserless_ws_endpoint()
    if endpoint:
        browser = await playwright.chromium.connect(endpoint)
    else:
        browser = await playwright.chromium.launch(headless=_is_headless())
    context_kwargs: dict[str, Any] = {}
    if record_har_path:
        context_kwargs["record_har_path"] = record_har_path
        context_kwargs["record_har_mode"] = "full"
        context_kwargs["record_har_content"] = "embed"
    browser_context = await browser.new_context(**context_kwargs)
    page = await browser_context.new_page()
    return browser, browser_context, page
