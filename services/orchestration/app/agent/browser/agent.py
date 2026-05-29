from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING, Any

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.utils import get_model, log_claude_step, with_structured_output

# Local workflow overrides live here. Any file named <id>.json takes precedence
# over the remote netgent-workflow library for that id, allowing local edits
# without touching the shared upstream repo.
_LOCAL_WORKFLOWS_DIR = (
    pathlib.Path(__file__).parent.parent.parent / "config" / "workflows"
)

if TYPE_CHECKING:
    from main import NetGent


class BrowserWorkflowGenerationState(MessagesState):
    intent: str
    workflow: dict[str, Any]
    parameters: dict[str, Any] | None = None
    reasoning: str
    workflow_source: str
    workflow_id: str | None


class BrowserWorkflowContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    netgent: NetGent


class ChooseWorkflow(BaseModel):
    is_valid: bool
    reasoning: str
    id: str | None = None
    parameters: dict[str, Any] | None = None


def _load_workflow(workflow_id: str, remote_link: str | None) -> dict[str, Any]:
    """Return workflow JSON, preferring a local override over the remote link.

    Checks _LOCAL_WORKFLOWS_DIR/<workflow_id>.json first. If that file exists
    it is loaded and returned immediately (no network call). Otherwise falls
    back to fetching remote_link if provided.
    """
    local_path = _LOCAL_WORKFLOWS_DIR / f"{workflow_id}.json"
    if local_path.is_file():
        print(f"[BROWSER WF] Using local workflow override: {local_path}")
        with local_path.open() as f:
            return json.load(f)
    if remote_link:
        try:
            return requests.get(remote_link, timeout=10).json()
        except Exception:
            pass
    return {"id": workflow_id}


def choose_workflow(
    state: BrowserWorkflowGenerationState, runtime: Runtime[BrowserWorkflowContext]
) -> dict[str, Any]:
    """Pick a browser workflow per workflow_source / workflow_id.

    Modes mirror the shell agent. There is currently no generate fallback for
    browser workflows, so `auto` and `library` behave the same when no library
    entry matches: the orchestrator routes to fail_no_workflow.
    """
    intent = state["intent"]
    workflow_source = (state.get("workflow_source") or "auto").lower()
    if workflow_source not in {"auto", "library", "generate"}:
        workflow_source = "auto"
    pinned_id = (state.get("workflow_id") or "").strip() or None

    WORKFLOW_INDEX_URL = "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows/index.json"
    try:
        available = [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "browser"
        ]
    except Exception:
        available = []
    print(
        f"[BROWSER WF] workflow_source={workflow_source!r} "
        f"pinned_workflow_id={pinned_id!r} library_size={len(available)}"
    )

    if workflow_source == "generate":
        reasoning = (
            "workflow_source=generate is not supported for browser workflows yet. "
            "Submit with workflow_source=auto or workflow_source=library."
        )
        print(f"[BROWSER WF] {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
        }

    if pinned_id:
        chosen_entry = next((w for w in available if w.get("id") == pinned_id), None)
        # Allow a local override even when the id isn't in the remote index.
        local_path = _LOCAL_WORKFLOWS_DIR / f"{pinned_id}.json"
        if chosen_entry is None and not local_path.is_file():
            reasoning = (
                f"Requested workflow id {pinned_id!r} not present in the browser "
                "workflow library."
            )
            print(f"[BROWSER WF] {reasoning}")
            return {
                "workflow": {},
                "parameters": None,
                "reasoning": reasoning,
            }
        remote_link = chosen_entry.get("link") if chosen_entry else None
        workflow = _load_workflow(pinned_id, remote_link)
        workflow.setdefault("id", pinned_id)
        return {
            "workflow": workflow,
            "parameters": None,
            "reasoning": f"Pinned browser workflow {pinned_id!r} via request workflow_id.",
        }

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
    remote_link = chosen_entry.get("link") if chosen_entry else None
    workflow = _load_workflow(result.id, remote_link) if result.id else {}

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
