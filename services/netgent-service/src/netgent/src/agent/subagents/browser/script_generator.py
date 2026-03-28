import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from browser_use.agent.views import AgentHistoryList

BOOKKEEPING_ACTIONS = {
    "done",
    "extract_page_content",
    "replace_file_str",
    "write_file",
}


def save_history_and_script(
    *,
    task: str,
    history: AgentHistoryList,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    history_path = output_dir / "history.json"
    script_path = output_dir / "workflow.py"
    manifest_path = output_dir / "manifest.json"

    history.save_to_file(history_path)
    script_content, warnings = build_playwright_script(task=task, history=history)
    script_path.write_text(script_content, encoding="utf-8")

    manifest = {
        "task": task,
        "final_result": history.final_result(),
        "is_done": history.is_done(),
        "is_successful": history.is_successful(),
        "history_path": str(history_path),
        "script_path": str(script_path),
        "warnings": warnings,
        "action_names": history.action_names(),
        "urls": history.urls(),
        "steps": history.number_of_steps(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "history_path": str(history_path),
        "script_path": str(script_path),
        "manifest_path": str(manifest_path),
        "script_warnings": warnings,
    }


def build_playwright_script(
    *, task: str, history: AgentHistoryList
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    body_lines: list[str] = []

    for step_index, action in enumerate(history.model_actions(), start=1):
        action_name, payload = _extract_action(action)
        if action_name is None or payload is None:
            warnings.append(f"Step {step_index}: could not decode action payload.")
            continue

        if action_name in BOOKKEEPING_ACTIONS:
            continue

        interacted_element = action.get("interacted_element")
        rendered = _render_action(
            step_index=step_index,
            action_name=action_name,
            payload=payload,
            interacted_element=interacted_element,
            warnings=warnings,
        )
        if rendered:
            body_lines.extend(rendered)

    if not body_lines:
        body_lines.append("    raise RuntimeError('No browser actions were captured.')")

    warnings_block = _format_warning_block(warnings)
    body = "\n".join(body_lines)
    task_literal = json.dumps(task)

    script = f"""import asyncio
import os
from pathlib import Path

from playwright.async_api import Locator, Page, async_playwright

TASK = {task_literal}
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
ARTIFACTS_DIR = Path(os.getenv("PLAYWRIGHT_ARTIFACTS_DIR", "artifacts/replay"))

{warnings_block}

async def resolve_locator(page: Page, selectors: list[str]) -> Locator:
    last_error: Exception | None = None
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=5_000)
            return locator
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Unable to resolve selector candidates: {{selectors}}") from last_error


async def run_task(page: Page) -> None:
{body}


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await run_task(page)
        finally:
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(ARTIFACTS_DIR / "storage_state.json"))
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
"""
    return script, warnings


def _render_action(
    *,
    step_index: int,
    action_name: str,
    payload: dict[str, Any],
    interacted_element: Any,
    warnings: list[str],
) -> list[str]:
    comment = f"    # Step {step_index}: {action_name}"

    if action_name == "go_to_url":
        url = payload["url"]
        if payload.get("new_tab"):
            return [
                comment,
                "    page = await page.context.new_page()",
                f"    await page.goto({json.dumps(url)})",
            ]
        return [comment, f"    await page.goto({json.dumps(url)})"]

    if action_name == "click_element_by_index":
        selectors = _selector_candidates(interacted_element)
        if not selectors:
            warnings.append(
                f"Step {step_index}: click action had no selector metadata; replay will need manual repair."
            )
            return [
                comment,
                "    # Manual action required: click target could not be reconstructed.",
            ]
        selector_list = _format_selector_list(selectors)
        return [
            comment,
            f"    await (await resolve_locator(page, {selector_list})).click()",
        ]

    if action_name == "input_text":
        selectors = _selector_candidates(interacted_element)
        text = payload["text"]
        if not selectors:
            warnings.append(
                f"Step {step_index}: input action had no selector metadata; replay will need manual repair."
            )
            return [
                comment,
                f"    # Manual action required: fill target with {json.dumps(text)}.",
            ]
        selector_list = _format_selector_list(selectors)
        return [
            comment,
            f"    await (await resolve_locator(page, {selector_list})).fill({json.dumps(text)})",
        ]

    if action_name == "upload_file":
        selectors = _selector_candidates(interacted_element)
        path = payload["path"]
        if not selectors:
            warnings.append(
                f"Step {step_index}: upload action had no selector metadata; replay will need manual repair."
            )
            return [
                comment,
                f"    # Manual action required: upload {json.dumps(path)}.",
            ]
        selector_list = _format_selector_list(selectors)
        return [
            comment,
            f"    await (await resolve_locator(page, {selector_list})).set_input_files({json.dumps(path)})",
        ]

    if action_name == "scroll":
        pages = float(payload.get("num_pages", 1.0))
        amount = int((1 if payload.get("down", True) else -1) * 900 * pages)
        return [comment, f"    await page.evaluate('window.scrollBy(0, {amount})')"]

    if action_name == "wait":
        seconds = int(payload.get("seconds", 0))
        return [comment, f"    await page.wait_for_timeout({seconds * 1000})"]

    if action_name == "send_keys":
        keys = payload["keys"]
        return [comment, f"    await page.keyboard.press({json.dumps(keys)})"]

    if action_name == "switch_tab":
        page_id = int(payload["page_id"])
        return [comment, f"    page = page.context.pages[{page_id}]"]

    if action_name == "close_tab":
        page_id = int(payload["page_id"])
        return [
            comment,
            f"    await page.context.pages[{page_id}].close()",
            "    page = page.context.pages[0]",
        ]

    warnings.append(
        f"Step {step_index}: unsupported action {action_name!r} was skipped."
    )
    return [comment, f"    # Unsupported action skipped: {action_name}"]


def _extract_action(action: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    action_name = next((key for key in action if key != "interacted_element"), None)
    if action_name is None:
        return None, None
    payload = action.get(action_name)
    if not isinstance(payload, dict):
        return None, None
    return action_name, payload


def _selector_candidates(interacted_element: Any) -> list[str]:
    if interacted_element is None:
        return []

    if is_dataclass(interacted_element):
        element = asdict(interacted_element)
    elif isinstance(interacted_element, dict):
        element = interacted_element
    else:
        element = interacted_element.__dict__

    attributes = element.get("attributes") or {}
    tag_name = element.get("tag_name") or ""
    candidates: list[str] = []

    def add(selector: str | None) -> None:
        if selector and selector not in candidates:
            candidates.append(selector)

    add(_tagged_attr_selector(tag_name, "id", attributes.get("id")))
    add(_tagged_attr_selector(tag_name, "name", attributes.get("name")))
    add(_tagged_attr_selector(tag_name, "placeholder", attributes.get("placeholder")))
    add(_tagged_attr_selector(tag_name, "aria-label", attributes.get("aria-label")))
    add(_tagged_attr_selector(tag_name, "title", attributes.get("title")))
    add(_tagged_attr_selector(tag_name, "data-testid", attributes.get("data-testid")))
    add(_tagged_attr_selector(tag_name, "role", attributes.get("role")))

    href = attributes.get("href")
    if href and tag_name == "a":
        add(f'a[href="{_escape_css_value(href)}"]')

    css_selector = element.get("css_selector")
    if css_selector:
        add(css_selector)

    xpath = element.get("xpath")
    if xpath:
        add(f"xpath={xpath}")

    return candidates


def _tagged_attr_selector(tag_name: str, name: str, value: str | None) -> str | None:
    if not value:
        return None
    prefix = tag_name if tag_name else ""
    return f'{prefix}[{name}="{_escape_css_value(value)}"]'


def _escape_css_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_selector_list(selectors: list[str]) -> str:
    return "[" + ", ".join(json.dumps(selector) for selector in selectors) + "]"


def _format_warning_block(warnings: list[str]) -> str:
    if not warnings:
        return "SCRIPT_WARNINGS: list[str] = []"

    lines = ["SCRIPT_WARNINGS = ["]
    for warning in warnings:
        lines.append(f"    {json.dumps(warning)},")
    lines.append("]")
    return "\n".join(lines)
