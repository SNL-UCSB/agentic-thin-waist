import asyncio
import json
import os
import tempfile
from typing import Any, NotRequired

from langgraph.graph import END, START, MessagesState
from langgraph.graph.state import StateGraph
from playwright.async_api import async_playwright

from netgent.src.agent.subagents.browser.execute.agent import (
    create_agent as create_execute_agent,
)
from netgent.src.agent.subagents.browser.generate.agent import (
    create_agent as create_browser_generate_agent,
)
from netgent.src.agent.subagents.browser.util import open_browser_session
from netgent.src.engine.controller import ProgramController
from netgent.src.engine.executor import StateExecutor
from netgent.src.engine.runner import WorkflowRunner
from netgent.src.registry.actions.playwright import PLAYWRIGHT_ACTIONS
from netgent.src.registry.triggers.base import always_true
from netgent.src.registry.triggers.playwright import PLAYWRIGHT_TRIGGERS


class BrowserState(MessagesState):
    task: str
    workflow: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    generate_result: dict[str, Any] | None = None
    steps: NotRequired[int]


def route_run_workflow(state: BrowserState):
    if state.get("workflow"):
        return "run_workflow"
    return "generate_workflow"


async def generate_workflow(state: BrowserState) -> dict[str, Any]:
    playwright = await async_playwright().start()
    generate_agent = create_browser_generate_agent()
    try:
        response = await generate_agent.ainvoke(
            {
                "task": state["task"],
                "messages": [],
                "steps": state.get("steps"),
            },
            context={"playwright": playwright},
        )

        return {
            "generate_result": response.get("result"),
            "workflow": response.get("workflow"),
        }
    finally:
        await playwright.stop()


def route_run_generated_workflow(state: BrowserState):
    result = state.get("generate_result")
    workflow = state.get("workflow")
    if isinstance(result, dict) and result.get("success", False):
        if isinstance(workflow, dict):
            return "run_workflow"
    return END


async def run_workflow(state: BrowserState) -> dict[str, Any]:
    workflow = state.get("workflow")
    if not isinstance(workflow, dict):
        return {
            "result": {
                "success": False,
                "error": "Workflow must be generated before running it",
            }
        }
    agent = create_execute_agent()
    playwright = await async_playwright().start()
    har_file = tempfile.NamedTemporaryFile(suffix=".har", delete=False)
    har_file.close()
    har_path = har_file.name
    browser_instance, browser_context, page = await open_browser_session(
        playwright, record_har_path=har_path
    )
    runner = WorkflowRunner(
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
    response: dict[str, Any] | None = None
    try:
        response = await agent.ainvoke(
            {
                "task": state["task"],
                "messages": state["messages"],
                "workflow": workflow,
            },
            context={
                "playwright": playwright,
                "browser": browser_instance,
                "browser_context": browser_context,
                "page": page,
                "runner": runner,
            },
        )
    except Exception as exc:
        response = {
            "result": {
                "success": False,
                "error": str(exc),
            }
        }
    finally:
        await browser_context.close()
        await browser_instance.close()
        await playwright.stop()

    har_result: dict[str, Any] | None = None
    if os.path.exists(har_path):
        try:
            har_result = json.loads(open(har_path, encoding="utf-8").read())
        except Exception:
            har_result = None
        finally:
            try:
                os.unlink(har_path)
            except OSError:
                pass
    response_result = response.get("result") if isinstance(response, dict) else None
    if isinstance(response_result, dict):
        final_result = dict(response_result)
        final_result["har"] = har_result
    else:
        final_result = {
            "data": response_result,
            "har": har_result,
        }
    return {
        "result": final_result,
        "workflow": response.get("workflow", workflow)
        if isinstance(response, dict)
        else workflow,
    }


def create_agent():
    graph = StateGraph(state_schema=BrowserState)
    graph.add_node("generate_workflow", generate_workflow)
    graph.add_node("run_workflow", run_workflow)
    graph.add_conditional_edges(
        START,
        route_run_workflow,
        {
            "generate_workflow": "generate_workflow",
            "run_workflow": "run_workflow",
        },
    )
    graph.add_conditional_edges(
        "generate_workflow",
        route_run_generated_workflow,
        {
            "run_workflow": "run_workflow",
            END: END,
        },
    )
    graph.add_edge("run_workflow", END)
    return graph.compile()


async def main():
    task = (
        "Run a simple browser workflow. "
        "First navigate to a test page. "
        "Second wait for 5 seconds."
    )
    workflow = {
        "specification": (
            "Run a simple browser workflow. "
            "First navigate to a test page. "
            "Second wait for 5 seconds."
        ),
        "states": [
            {
                "checks": [{"type": "always_true", "params": {}}],
                "actions": [
                    {
                        "type": "go_to_url",
                        "params": {
                            "url": "data:text/html,<html><body><h1>Workflow Runner Test</h1></body></html>",
                            "new_tab": False,
                        },
                    },
                    {
                        "type": "wait",
                        "params": {"seconds": 5},
                    },
                ],
                "end_state": "Workflow Completed",
            }
        ],
    }
    browser_agent = create_agent()
    response = await browser_agent.ainvoke(
        {
            "task": os.getenv("BROWSER_USE_TASK", task),
            "messages": [],
            "workflow": workflow,
        },
    )
    print(response)
    return response


if __name__ == "__main__":
    asyncio.run(main())
