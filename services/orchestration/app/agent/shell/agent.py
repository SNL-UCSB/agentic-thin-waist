from __future__ import annotations

from typing import TYPE_CHECKING, Any

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.utils import get_model

if TYPE_CHECKING:
    from clients.netgent.src.main import NetGent


class ShellWorkflowGenerationState(MessagesState):
    intent: str
    workflow: dict[str, Any]
    chosen_workflow: dict[str, Any] | None
    parameters: dict[str, Any] | None
    reasoning: str


class ShellWorkflowContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    netgent: NetGent


class ChooseWorkflow(BaseModel):
    is_valid: bool
    reasoning: str
    id: str | None = None
    parameters: dict[str, Any] | None = None


WORKFLOW_INDEX_URL = "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows/index.json"


def choose_workflow(
    state: ShellWorkflowGenerationState, runtime: Runtime[ShellWorkflowContext]
) -> dict[str, Any]:
    """Ask Claude to pick an existing NetGent shell workflow that fits the intent."""
    intent = state["intent"]

    try:
        available = [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "shell"
        ]
    except Exception:
        available = []

    workflows_block = (
        "\n".join(
            f"- id: {w['id']}\n  name: {w.get('name', '')}\n  description: {w.get('description', '')}\n  parameters: {w.get('parameters', [])}"
            for w in available
        )
        if available
        else "(none available)"
    )

    prompt = [
        HumanMessage(
            content=(
                f"You are selecting a pre-built shell workflow for a network experiment.\n\n"
                f"Intent: {intent}\n\n"
                f"Available workflows:\n{workflows_block}\n\n"
                "If an existing workflow matches the intent well, set is_valid=true and provide its id and parameters. "
                "Otherwise set is_valid=false and explain in reasoning."
            )
        )
    ]

    model = get_model()
    result: ChooseWorkflow = model.with_structured_output(ChooseWorkflow).invoke(prompt)

    chosen_entry = next((w for w in available if w["id"] == result.id), None)
    if chosen_entry and chosen_entry.get("link"):
        try:
            workflow = requests.get(chosen_entry["link"], timeout=10).json()
        except Exception:
            workflow = {"id": result.id}
    else:
        workflow = {"id": result.id}

    return {
        "workflow": workflow,
        "parameters": result.parameters,
        "reasoning": result.reasoning,
        "chosen_workflow": result.model_dump(),
    }


def route_valid_workflow(state: ShellWorkflowGenerationState) -> str:
    """Route based on whether the chosen workflow is valid."""
    chosen = state.get("chosen_workflow")
    if chosen and chosen.get("is_valid"):
        return "choose_workflow"
    return "generate"


def generate(
    state: ShellWorkflowGenerationState, runtime: Runtime[ShellWorkflowContext]
) -> dict[str, Any]:
    """Generate a shell workflow from the intent using the NetGent shell subagent."""
    from clients.netgent.src.agent.subagents.shell.agent import (
        create_agent as create_shell_netgent_agent,
    )
    from clients.netgent.src.engine.controller import ProgramController
    from clients.netgent.src.engine.executor import StateExecutor
    from clients.netgent.src.engine.runner import WorkflowRunner
    from clients.netgent.src.registry.actions.network import NETWORK_ACTIONS
    from clients.netgent.src.registry.triggers.base_action import always_true

    intent = state["intent"]
    runner = WorkflowRunner(
        controller=ProgramController(triggers=(always_true,)),
        executor=StateExecutor(actions=NETWORK_ACTIONS),
    )
    agent = create_shell_netgent_agent()
    result = agent.invoke(
        {"task": intent, "messages": [], "workflow": None, "parameters": {}},
        context={"runner": runner},
    )
    workflow = result.get("workflow") or {}
    return {"workflow": workflow}


def create_agent():
    """Build and compile the shell workflow generation agent."""
    graph = StateGraph(
        state_schema=ShellWorkflowGenerationState,
        context_schema=ShellWorkflowContext,
    )

    graph.add_node("choose_workflow", choose_workflow)
    graph.add_node("generate", generate)

    graph.add_edge(START, "choose_workflow")
    graph.add_conditional_edges(
        "choose_workflow",
        route_valid_workflow,
        {"choose_workflow": END, "generate": "generate"},
    )
    graph.add_edge("generate", END)

    return graph.compile()
