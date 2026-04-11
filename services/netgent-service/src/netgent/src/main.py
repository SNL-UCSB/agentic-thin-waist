"""NetGent client — run workflows directly via the netgent engine (no HTTP)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

from netgent.src.agent.agent import create_agent

WorkflowType = Literal["browser", "shell", "hybrid"]


class NetGent:
    """Direct client for running NetGent workflows.

    Calls the agent and engine in-process — no API server required.

    Example:
        import asyncio
        from netgent.src.main import NetGent

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

    def __init__(self) -> None:
        pass

    # ── generate_and_run ──────────────────────────────────────────────────────

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
        agent = create_agent()
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

        agent = create_agent()
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
