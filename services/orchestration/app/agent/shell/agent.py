from __future__ import annotations

import json
import os
import pathlib
from typing import TYPE_CHECKING, Any

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.utils import get_model, log_claude_step

if TYPE_CHECKING:
    from clients.netgent.src.main import NetGent

WORKFLOW_INDEX_URL = "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows/index.json"
_SCHEMAS_PATH = (
    pathlib.Path(__file__).parent.parent.parent / "config" / "workflow_schemas.json"
)
_WORKFLOW_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = (
    json.loads(_SCHEMAS_PATH.read_text()) if _SCHEMAS_PATH.exists() else {}
)


def _build_param_hint(workflow_id: str, param_names: list[str]) -> str:
    schema = _WORKFLOW_SCHEMAS.get(workflow_id, {})
    parts: list[str] = []
    for name in param_names:
        if name in schema:
            meta = schema[name]
            parts.append(
                f"{name} ({meta['type']}, default={meta['default']}): {meta['description']}"
            )
        else:
            parts.append(name)
    return "[" + ", ".join(parts) + "]"


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
            f"- id: {w['id']}\n  name: {w.get('name', '')}\n  description: {w.get('description', '')}\n  parameters: {_build_param_hint(w['id'], w.get('parameters', []))}"
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
                "Otherwise set is_valid=false and explain in reasoning.\n\n"
                "IMPORTANT: For boolean parameters output exactly true or false — never a number."
            )
        )
    ]

    model = get_model()
    log_claude_step(
        "shell_choose_workflow",
        prompt="\n\n".join(
            str(msg.content) for msg in prompt if hasattr(msg, "content")
        ),
    )
    result: ChooseWorkflow = model.with_structured_output(ChooseWorkflow).invoke(prompt)
    print(
        f"[SHELL WF] LLM choose_workflow: is_valid={result.is_valid} id={result.id!r} params={result.parameters}"
    )
    log_claude_step(
        "shell_choose_workflow",
        reasoning=result.reasoning,
        output=result.model_dump(),
    )

    chosen_entry = next((w for w in available if w["id"] == result.id), None)
    reasoning = result.reasoning
    has_creds = bool(
        os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )

    if result.is_valid and chosen_entry and chosen_entry.get("link"):
        try:
            workflow = requests.get(chosen_entry["link"], timeout=10).json()
            workflow.setdefault("id", result.id)
        except Exception:
            workflow = {"id": result.id}
    elif result.is_valid and result.id:
        workflow = {"id": result.id}
    else:
        # is_valid=False: return empty workflow so orchestration ends via fail_no_workflow.
        workflow = {}
        if not has_creds:
            reasoning = (
                f"{result.reasoning} Workflow not present for this intent or invalid request, "
                "and workflow generation is unavailable because Google credentials are not configured."
            )
            print(
                "[SHELL WF] Invalid/no matching workflow and no Google creds; failing request"
            )

    return {
        "workflow": workflow,
        "parameters": result.parameters,
        "reasoning": reasoning,
        "chosen_workflow": result.model_dump(),
    }


def route_valid_workflow(state: ShellWorkflowGenerationState) -> str:
    """Route based on whether the chosen workflow is valid."""
    chosen = state.get("chosen_workflow")
    if chosen and chosen.get("is_valid"):
        print(
            f"[SHELL WF] route_valid_workflow: is_valid=True, id={chosen.get('id')!r}"
        )
        return "choose_workflow"
    has_creds = bool(
        os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )
    print(
        f"[SHELL WF] route_valid_workflow: is_valid=False, has_google_creds={has_creds}"
    )
    if not has_creds:
        print("[SHELL WF] No Google creds — ending with invalid/missing workflow")
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
