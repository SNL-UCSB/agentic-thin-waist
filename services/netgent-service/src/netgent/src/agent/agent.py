from typing import Literal

from engine.controller import ProgramController
from engine.executor import StateExecutor
from engine.runner import WorkflowRunner
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, MessagesState
from langgraph.graph.state import StateGraph
from playwright.async_api import async_playwright
from registry.actions.network import NETWORK_ACTIONS
from registry.triggers.base import always_true

from agent.subagents.browser.agent import create_agent as create_browser_agent
from agent.subagents.shell.agent import create_agent as create_shell_agent

model = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview")


class NetGentState(MessagesState):
    task: str
    type: Literal["browser", "shell"] = "browser"
    workflow: dict = {}
    result: list = []
    config: dict = {}


# Routes the Type
def route_type(state: NetGentState):
    if state["type"] == "browser":
        return "browser"
    elif state["type"] == "shell":
        return "shell"
    return END


async def browser(state: NetGentState):
    playwright = await async_playwright().start()
    browser_agent = create_browser_agent()

    try:
        response = await browser_agent.ainvoke(
            {"task": state["task"]},
            context={"playwright": playwright},
        )
        return response
    finally:
        await playwright.stop()


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
            "messages": state["messages"],
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


def main():
    task = (
        "Run all three tools one by one in a single workflow. "
        "First run ping against google.com. "
        "Second run iperf3 against host speedtest.sfo12.us.leaseweb.net on port 5201. "
        "Third run ndt7 with default settings. "
        "After all three tool calls complete, summarize the results."
    )

    workflow = {
        "specification": "Run all three tools one by one in a single workflow. First run ping against google.com. Second run iperf3 against host speedtest.sfo12.us.leaseweb.net on port 5201. Third run ndt7 with default settings. After all three tool calls complete, summarize the results.",
        "states": [
            {
                "checks": [{"type": "always_true", "params": {}}],
                "actions": [
                    {"type": "ping", "params": {"host": "google.com"}},
                    {
                        "type": "iperf",
                        "params": {
                            "host": "speedtest.sfo12.us.leaseweb.net",
                            "port": 5201,
                        },
                    },
                    {"type": "ndt", "params": {}},
                ],
                "end_state": "Workflow Completed",
            }
        ],
    }

    agent = create_agent()
    result = agent.invoke(
        {"task": task, "messages": [], "workflow": workflow, "type": "shell"},
    )
    print(result)
