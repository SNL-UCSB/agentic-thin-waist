"""NetGent client — run workflows directly via the netgent engine (no HTTP)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

WorkflowType = Literal["browser", "shell", "hybrid"]


class NetGent:
    """Direct client for running NetGent workflows.

    Calls the agent and engine in-process — no API server required.

    Example:
        import asyncio
        from clients.netgent import NetGent

        client = NetGent()

        # Generate a workflow from natural language and run it
        result = asyncio.run(client.generate("Ping 8.8.8.8 three times", type="shell"))

        # Execute a pre-built workflow with parameters
        workflow = {
            "specification": "Ping a host",
            "states": [{
                "checks": [{"type": "always_true", "params": {}}],
                "actions": [{"type": "ping", "params": {"host": "{{host}}", "count": "{{count}}"}}],
            }],
            "parameters": ["host", "count"],
        }
        result = asyncio.run(client.execute(workflow, parameters={"host": "8.8.8.8", "count": "3"}))
    """

    def __init__(
        self,
        *,
        cdp_url: str | None = None,
        headless: bool = False,
    ) -> None:
        """Create a NetGent client.

        Args:
            cdp_url:  Remote Chromium CDP URL (e.g. ``ws://browserless:3000/...``).
                      When truthy, browser workflows use **CDP mode** and connect
                      to the remote browser. When ``None`` or empty, uses
                      **Local mode** and launches Chromium on this machine.
            headless: In Local mode, run Chromium headless. Defaults to ``False``
                      (visible browser). Ignored in CDP mode.
        """
        self.cdp_url = cdp_url
        self.headless = headless
        # Propagate to env vars so the internal LLM agent / browser_use
        # (which read these directly) pick up the same configuration.
        os.environ["BROWSERLESS_WS_ENDPOINT"] = cdp_url or ""
        os.environ["BROWSER_USE_HEADLESS"] = "true" if headless else "false"

    @staticmethod
    def _create_agent() -> Any:
        from clients.netgent.src.agent.agent import create_agent

        return create_agent()

    @staticmethod
    def _build_runner(
        *,
        runtime: WorkflowType = "shell",
        parameters: dict[str, str] | None = None,
        context: Any = None,
    ) -> Any:
        """Build a WorkflowRunner for the given runtime type.

        Does **not** import the LLM agent, so this works in environments
        without langchain / google-genai installed.
        """
        from clients.netgent.src.engine.controller import ProgramController
        from clients.netgent.src.engine.executor import StateExecutor
        from clients.netgent.src.engine.runner import WorkflowRunner
        from clients.netgent.src.registry.actions.network import NETWORK_ACTIONS
        from clients.netgent.src.registry.triggers.base_action import always_true

        actions = NETWORK_ACTIONS
        triggers = (always_true,)

        if runtime in ("browser", "hybrid"):
            from clients.netgent.src.registry.actions.playwright import (
                PLAYWRIGHT_ACTIONS,
            )
            from clients.netgent.src.registry.triggers.playwright import (
                PLAYWRIGHT_TRIGGERS,
            )

            actions = (*NETWORK_ACTIONS, *PLAYWRIGHT_ACTIONS)
            triggers = (always_true, *PLAYWRIGHT_TRIGGERS)

        return WorkflowRunner(
            controller=ProgramController(triggers=triggers),
            executor=StateExecutor(
                actions=actions, parameters=parameters, context=context
            ),
        )

    # ── run_workflow (engine-only, no LLM) ────────────────────────────────────

    def run_workflow(
        self,
        workflow: dict[str, Any],
        *,
        parameters: dict[str, str] | None = None,
        type: WorkflowType | None = None,
        record_har: bool = False,
    ) -> dict[str, Any]:
        """Execute a workflow directly through the engine — no LLM agent required.

        This is the lightweight path for running pre-built workflows in
        environments that do not have the LLM dependencies installed
        (e.g. the substrate-worker container).

        For browser/hybrid workflows, selects between two modes based on
        the ``cdp_url`` passed to ``NetGent(...)``:

        * **CDP mode** — if ``cdp_url`` is set, connects to the remote Chromium
          instance (e.g. Browserless) via CDP.
        * **Local mode** — otherwise, launches Chromium on this machine.
          Headless is controlled by the ``headless=`` kwarg on ``NetGent(...)``
          (defaults to ``False`` / visible).

        Args:
            workflow:    Workflow dict with specification, states, etc.
            parameters:  Runtime values for ``{{placeholder}}`` fields.
            type:        ``"browser"``, ``"shell"``, or ``"hybrid"``.
                         Falls back to workflow-level ``"type"`` key, then ``"shell"``.
            record_har:  When True (browser/hybrid only), record a HAR archive
                         and include it in the result under the ``"har"`` key.

        Returns:
            A dict with ``"result"`` (list of per-state action results) and,
            for browser/hybrid workflows with *record_har*, a ``"har"`` key.
        """
        runtime: WorkflowType = type or workflow.get("type", "shell")

        if runtime in ("browser", "hybrid"):
            return asyncio.run(
                self._run_browser_workflow(
                    workflow,
                    runtime=runtime,
                    parameters=parameters,
                    record_har=record_har,
                )
            )

        runner = self._build_runner(runtime=runtime, parameters=parameters)
        return {"result": runner.run(workflow)}

    async def _run_browser_workflow(
        self,
        workflow: dict[str, Any],
        *,
        runtime: WorkflowType,
        parameters: dict[str, str] | None = None,
        record_har: bool = False,
    ) -> dict[str, Any]:
        """Open a CDP browser session, run the workflow, then tear down.

        Returns a dict with ``result`` (list of per-state action results)
        and, when *record_har* is True, a ``har`` key containing the
        recorded HAR data.
        """
        import tempfile

        from playwright.async_api import async_playwright

        endpoint = (self.cdp_url or "").strip()
        har_path: str | None = None

        if record_har:
            har_file = tempfile.NamedTemporaryFile(suffix=".har", delete=False)
            har_file.close()
            har_path = har_file.name

        async with async_playwright() as pw:
            from clients.netgent.src.agent.subagents.browser.util import (
                GPU_RENDERING_ARGS,
                MEDIA_STREAM_DISABLE_ARGS,
                STEALTH_INIT_SCRIPT,
                STEALTH_LAUNCH_ARGS,
                STEALTH_USER_AGENT,
                _stealth_enabled,
            )

            stealth = _stealth_enabled()

            if endpoint:
                # CDP mode: connect to a remote browser (e.g. Browserless)
                browser = await pw.chromium.connect(endpoint)
            else:
                # Local mode: launch Chromium on this machine.
                launch_args = [*MEDIA_STREAM_DISABLE_ARGS, *GPU_RENDERING_ARGS]
                launch_kwargs: dict[str, Any] = {
                    "headless": self.headless,
                    "args": launch_args,
                }
                if stealth:
                    launch_kwargs["args"] = [*launch_args, *STEALTH_LAUNCH_ARGS]
                    launch_kwargs["ignore_default_args"] = ["--enable-automation"]
                browser = await pw.chromium.launch(**launch_kwargs)

            context_kwargs: dict[str, Any] = {
                "permissions": ["camera", "microphone"],
                "viewport": {"width": 1280, "height": 720},
            }
            if stealth:
                context_kwargs["user_agent"] = STEALTH_USER_AGENT
            if har_path:
                context_kwargs["record_har_path"] = har_path
                context_kwargs["record_har_mode"] = "full"
                context_kwargs["record_har_content"] = "embed"

            browser_context = await browser.new_context(**context_kwargs)
            if stealth:
                await browser_context.add_init_script(STEALTH_INIT_SCRIPT)
            page = await browser_context.new_page()

            try:
                from clients.netgent.src.registry.context import Context

                ctx = Context(page=page)
                runner = self._build_runner(
                    runtime=runtime, parameters=parameters, context=ctx
                )
                result = await runner.arun(workflow)
            finally:
                await browser_context.close()
                await browser.close()

        har_data: dict[str, Any] | None = None
        if har_path:
            try:
                with open(har_path, encoding="utf-8") as f:
                    har_data = json.load(f)
            except Exception:
                pass
            finally:
                try:
                    os.unlink(har_path)
                except OSError:
                    pass

        response: dict[str, Any] = {"result": result}
        if har_data is not None:
            response["har"] = har_data
        return response

    # ── generate (LLM agent) ─────────────────────────────────────────────────

    async def generate(
        self,
        specification: str,
        *,
        type: WorkflowType = "browser",
        parameters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Generate a workflow from a natural language specification and run it.

        The agent generates the workflow and immediately runs it in a single pass.
        Returns the full result including the generated workflow and execution output.
        """
        agent = self._create_agent()
        return await agent.ainvoke(
            {
                "task": specification,
                "messages": [],
                "workflow": {},
                "type": type,
                "parameters": parameters or {},
            }
        )

    # ── execute ────────────────────────────────────────────────────────────────

    async def execute(
        self,
        workflow: dict[str, Any],
        *,
        parameters: dict[str, str] | None = None,
        type: WorkflowType | None = None,
    ) -> dict[str, Any]:
        """Execute a pre-built workflow with optional parameter substitution.

        Use this when you already have a workflow definition (e.g. previously
        generated and saved). Parameters are substituted for {{placeholder}}
        fields in action params at runtime.

        Args:
            workflow:   Workflow dict with specification, states, and parameters.
            parameters: Runtime values for {{placeholder}} fields in action params.
            type:       Workflow type override (browser / shell / hybrid).
                        Falls back to workflow-level "type" key, then "browser".
        """
        workflow_type: WorkflowType = type or workflow.get("type", "browser")

        agent = self._create_agent()
        return await agent.ainvoke(
            {
                "task": workflow.get("specification", "Run workflow"),
                "messages": [],
                "workflow": workflow,
                "type": workflow_type,
                "parameters": parameters or {},
            }
        )


if __name__ == "__main__":
    os.environ["BROWSERLESS_WS_ENDPOINT"] = ""
    os.environ["BROWSERLESS_CDP_ENDPOINT"] = ""

    client = NetGent()

    # Example: execute a pre-built browser workflow with parameters
    workflow = {
        "specification": "Go to a website and wait",
        "states": [
            {
                "checks": [{"type": "always_true", "params": {}}],
                "actions": [
                    {
                        "type": "go_to_url",
                        "params": {"url": "{{url}}", "new_tab": False},
                    },
                    {"type": "wait", "params": {"seconds": "{{wait_seconds}}"}},
                ],
                "end_state": "done",
            }
        ],
        "parameters": ["url", "wait_seconds"],
    }

    result = asyncio.run(
        client.execute(
            workflow,
            parameters={"url": "https://example.com", "wait_seconds": "10"},
            type="browser",
        )
    )

    r = result.get("result", {})
    if isinstance(r, dict):
        print(
            json.dumps(
                {k: v for k, v in r.items() if k not in ("har",)}, indent=2, default=str
            )
        )
    else:
        print(json.dumps(r, indent=2, default=str))
