import asyncio
import base64
import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, MessagesState
from langgraph.graph.state import StateGraph

from netgent.src.agent.subagents.browser.agent import (
    create_agent as create_browser_agent,
)
from netgent.src.agent.subagents.shell.agent import create_agent as create_shell_agent
from netgent.src.engine.controller import ProgramController
from netgent.src.engine.executor import StateExecutor
from netgent.src.engine.runner import WorkflowRunner
from netgent.src.registry.actions.network import NETWORK_ACTIONS
from netgent.src.registry.triggers.base import always_true

model = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview")


class NetGentState(MessagesState):
    task: str
    type: Literal["browser", "shell"] = "browser"
    workflow: dict = {}
    result: list = []
    config: dict = {}


def _iter_result_screenshots(value: object, path: tuple[object, ...] = ()):
    if isinstance(value, dict):
        screenshot = value.get("screenshot")
        if isinstance(screenshot, dict):
            b64 = screenshot.get("b64")
            image_format = screenshot.get("format")
            if isinstance(b64, str) and b64 and isinstance(image_format, str):
                yield path, b64, image_format

        for key, nested_value in value.items():
            yield from _iter_result_screenshots(nested_value, (*path, key))
        return

    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            yield from _iter_result_screenshots(nested_value, (*path, index))


def _write_result_screenshot_artifacts(
    result: object,
    artifact_dir: Path,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    artifact_dir.mkdir(parents=True, exist_ok=True)

    for index, (path_parts, b64, image_format) in enumerate(
        _iter_result_screenshots(result),
        start=1,
    ):
        safe_format = image_format.lower().strip(".") or "png"
        filename = f"screenshot_{index:03d}.{safe_format}"
        file_path = artifact_dir / filename
        file_path.write_bytes(base64.b64decode(b64))
        artifacts.append(
            {
                "path": str(file_path),
                "format": safe_format,
                "source": " -> ".join(str(part) for part in path_parts),
            }
        )

    return artifacts


def _write_workflow_artifact(
    result: object,
    artifact_dir: Path,
) -> str | None:
    if not isinstance(result, dict):
        return None

    workflow = result.get("workflow")
    if not isinstance(workflow, dict):
        return None

    artifact_dir.mkdir(parents=True, exist_ok=True)

    workflow_json_path = artifact_dir / "generated_workflow.json"
    workflow_json_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return str(workflow_json_path)


# Routes the Type
def route_type(state: NetGentState):
    if state["type"] == "browser":
        return "browser"
    elif state["type"] == "shell":
        return "shell"
    return END


async def browser(state: NetGentState):
    browser_agent = create_browser_agent()
    return await browser_agent.ainvoke(
        {
            "task": state["task"],
            "messages": state["messages"],
            "workflow": state.get("workflow", None),
        },
    )


def shell(state: NetGentState):
    shell_agent = create_shell_agent()
    runner = WorkflowRunner(
        controller=ProgramController(triggers=(always_true,)),
        executor=StateExecutor(actions=NETWORK_ACTIONS),
        config={},
    )
    return shell_agent.invoke(
        {
            "task": state["task"],
            "messages": [],
            "workflow": state.get("workflow", None),
        },
        context={"runner": runner},
    )


def create_agent():
    graph = StateGraph(state_schema=NetGentState)
    graph.add_node("browser", browser)
    graph.add_node("shell", shell)
    graph.add_conditional_edges(
        START, route_type, {"browser": "browser", "shell": "shell", END: END}
    )
    graph.add_edge("browser", END)
    graph.add_edge("shell", END)
    return graph.compile()


async def main():

    wf = {
        "specification": "1. Watch a YouTube video (https://www.youtube.com/watch?v=RKBi_ouZPP8) for 30 seconds",
        "workflow": {
            "specification": "1. Go to YouTube, 2. Search for Silent and Quiet Video, 3. Click a Video and Wait/Watch it 30 Seconds",
            "states": [
                {
                    "checks": [{"type": "always_true", "params": {}}],
                    "actions": [
                        {
                            "type": "go_to_url",
                            "params": {
                                "url": "https://www.youtube.com",
                                "new_tab": False,
                            },
                        },
                        {
                            "type": "input_text",
                            "params": {
                                "selector": 'input[name="search_query"]',
                                "text": "Silent and Quiet Video",
                            },
                        },
                        {
                            "type": "click_element",
                            "params": {
                                "selector": 'button.ytSearchboxComponentSearchButton[aria-label="Search"]'
                            },
                        },
                        {
                            "type": "click_element",
                            "params": {"selector": 'div[id="searchbox-suggestion:19"]'},
                        },
                        {
                            "type": "click_element",
                            "params": {
                                "selector": 'button.ytSearchboxComponentSearchButton[aria-label="Search"]'
                            },
                        },
                        {
                            "type": "click_element",
                            "params": {"selector": 'a[id="thumbnail"]'},
                        },
                        {"type": "wait", "params": {"seconds": 30}},
                        {"type": "wait", "params": {"seconds": 10}},
                    ],
                    "end_state": "Workflow Completed",
                    "executed": [],
                }
            ],
        },
    }

    agent = create_agent()
    result = await agent.ainvoke(
        {
            "messages": [],
            "task": wf["specification"],
            "workflow": {},
            "type": "browser",
        },
    )
    artifacts = _write_result_screenshot_artifacts(
        result,
        Path("artifacts") / "browser",
    )
    if isinstance(result, dict):
        result["artifacts"] = artifacts
        workflow_artifact = _write_workflow_artifact(
            result,
            Path("artifacts") / "browser",
        )
        if workflow_artifact is not None:
            result["workflow_json_path"] = workflow_artifact
    result_json_path = Path("artifacts") / "browser" / "result.json"
    result_json_path.parent.mkdir(parents=True, exist_ok=True)
    result_json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    if isinstance(result, dict):
        result["result_json_path"] = str(result_json_path)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
