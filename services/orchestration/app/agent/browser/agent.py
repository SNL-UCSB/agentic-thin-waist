from __future__ import annotations

from typing import TYPE_CHECKING, Any

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.utils import get_model, log_claude_step, with_structured_output

if TYPE_CHECKING:
    from main import NetGent


class BrowserWorkflowGenerationState(MessagesState):
    intent: str
    workflow: dict[str, Any]
    parameters: dict[str, Any] | None = None
    reasoning: str


class BrowserWorkflowContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    netgent: NetGent


class ChooseWorkflow(BaseModel):
    is_valid: bool
    reasoning: str
    id: str | None = None
    parameters: dict[str, Any] | None = None


def choose_workflow(
    state: BrowserWorkflowGenerationState, runtime: Runtime[BrowserWorkflowContext]
) -> dict[str, Any]:
    """Ask Claude to pick an existing NetGent workflow that fits the intent."""
    intent = state["intent"]
    WORKFLOW_INDEX_URL = "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows/index.json"
    try:
        available = [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "browser"
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
                f"You are selecting a pre-built browser workflow for a network experiment.\n\n"
                f"Intent: {intent}\n\n"
                f"Available workflows:\n{workflows_block}\n\n"
                "If an existing workflow matches the intent well, set is_valid=true and provide its id and parameters. "
                "Otherwise set is_valid=false and explain in reasoning."
            )
        )
    ]

    model = get_model()
    log_claude_step(
        "browser_choose_workflow",
        prompt="\n\n".join(
            str(msg.content) for msg in prompt if hasattr(msg, "content")
        ),
    )
    result: ChooseWorkflow = with_structured_output(model, ChooseWorkflow).invoke(
        prompt
    )
    log_claude_step(
        "browser_choose_workflow",
        reasoning=result.reasoning,
        output=result.model_dump(),
    )

    if not result.is_valid:
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": result.reasoning,
        }

    chosen_entry = next((w for w in available if w["id"] == result.id), None)
    if chosen_entry and chosen_entry.get("link"):
        try:
            workflow = requests.get(chosen_entry["link"], timeout=10).json()
        except Exception:
            workflow = {}
    else:
        workflow = {}

    return {
        "workflow": workflow,
        "parameters": result.parameters,
        "reasoning": result.reasoning,
    }


def create_agent():
    """Build and compile the browser workflow generation agent."""
    graph = StateGraph(
        state_schema=BrowserWorkflowGenerationState,
        context_schema=BrowserWorkflowContext,
    )

    graph.add_node("choose_workflow", choose_workflow)

    graph.add_edge(START, "choose_workflow")
    graph.add_edge("choose_workflow", END)

    return graph.compile()
