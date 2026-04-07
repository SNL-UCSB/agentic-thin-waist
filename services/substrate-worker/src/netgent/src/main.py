from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal, cast

from playwright.async_api import Page, Playwright, async_playwright

from netgent.src.engine.controller import ProgramController
from netgent.src.engine.executor import StateExecutor
from netgent.src.engine.runner import WorkflowRunner
from netgent.src.registry.actions.network import NETWORK_ACTIONS
from netgent.src.registry.actions.playwright import PLAYWRIGHT_ACTIONS
from netgent.src.registry.triggers.base_action import always_true
from netgent.src.registry.triggers.playwright import PLAYWRIGHT_TRIGGERS

WorkflowRuntime = Literal["shell", "browser"]

LOCAL_BROWSERLESS_WS_ENDPOINT = "ws://127.0.0.1:3000/chromium/playwright"


async def open_browser_session(
    playwright: Playwright, *, record_har_path: str | None = None
):
    browser = await playwright.chromium.connect(
        LOCAL_BROWSERLESS_WS_ENDPOINT,
    )

    context_kwargs: dict[str, Any] = {}
    if record_har_path:
        context_kwargs["record_har_path"] = record_har_path
        context_kwargs["record_har_mode"] = "full"
        context_kwargs["record_har_content"] = "embed"

    browser_context = await browser.new_context(**context_kwargs)
    page = await browser_context.new_page()
    return browser, browser_context, page


def build_shell_runner() -> WorkflowRunner:
    return WorkflowRunner(
        controller=ProgramController(triggers=(always_true,)),
        executor=StateExecutor(actions=NETWORK_ACTIONS),
        config={},
    )


def build_browser_runner(*, page: Page) -> WorkflowRunner:
    return WorkflowRunner(
        controller=ProgramController(
            triggers=(always_true, *PLAYWRIGHT_TRIGGERS),
            context={"page": page},
        ),
        executor=StateExecutor(
            actions=PLAYWRIGHT_ACTIONS,
            context={"page": page},
        ),
        config={},
    )


def load_workflow(
    *,
    workflow_path: str | Path | None = None,
    workflow_json: str | None = None,
) -> dict[str, Any]:
    if workflow_json:
        payload = json.loads(workflow_json)
    else:
        raw_path = (
            str(workflow_path)
            if workflow_path is not None
            else os.getenv("NETGENT_WORKFLOW_PATH", "").strip()
        )
        if not raw_path:
            raise RuntimeError(
                "Provide a workflow via NETGENT_WORKFLOW_JSON or NETGENT_WORKFLOW_PATH."
            )
        resolved_path = Path(raw_path)
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Workflow payload must decode to a JSON object")
    return payload


def _load_har_result(har_path: str) -> dict[str, Any] | None:
    if not os.path.exists(har_path):
        return None

    try:
        with open(har_path, encoding="utf-8") as har_file:
            return json.load(har_file)
    except Exception:
        return None
    finally:
        try:
            os.unlink(har_path)
        except OSError:
            pass


async def run_shell_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    runner = build_shell_runner()
    return {
        "runtime": "shell",
        "execution_mode": "local-container",
        "result": runner.run(workflow),
    }


async def run_browser_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    playwright = await async_playwright().start()
    har_file = tempfile.NamedTemporaryFile(suffix=".har", delete=False)
    har_file.close()
    har_path = har_file.name

    browser_instance, browser_context, page = await open_browser_session(
        playwright,
        record_har_path=har_path,
    )
    runner = build_browser_runner(page=page)

    try:
        output = await runner.arun(workflow)
        final_url = page.url
    finally:
        await browser_context.close()
        await browser_instance.close()
        await playwright.stop()

    return {
        "runtime": "browser",
        "result": output,
        "final_url": final_url,
        "har": _load_har_result(har_path),
    }


async def arun_workflow(
    workflow: dict[str, Any],
    *,
    runtime: WorkflowRuntime = "shell",
) -> dict[str, Any]:
    if runtime == "shell":
        return await run_shell_workflow(workflow)
    return await run_browser_workflow(workflow)


def run_workflow(
    workflow: dict[str, Any],
    *,
    runtime: WorkflowRuntime = "shell",
) -> dict[str, Any]:
    return asyncio.run(arun_workflow(workflow, runtime=runtime))


def main() -> None:
    workflow = load_workflow(
        workflow_json=os.getenv("NETGENT_WORKFLOW_JSON"),
    )
    runtime = cast(
        WorkflowRuntime,
        os.getenv("NETGENT_WORKFLOW_TYPE", "shell").strip() or "shell",
    )
    result = run_workflow(workflow, runtime=runtime)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
