from __future__ import annotations

import json
import os
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

_LOCAL_BROWSER_WORKFLOWS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "local_browser_workflows.json"
)


def _load_local_browser_workflows() -> list[dict]:
    """Load browser workflows from local config (e.g. Prudentia)."""
    try:
        with open(_LOCAL_BROWSER_WORKFLOWS_PATH) as f:
            return json.load(f)
    except Exception:
        return []


_PRUDENTIA_KEYWORD_MAP = {
    "youtube": "prudentia_youtube_vod_workflow",
    "vimeo": "prudentia_vimeo_vod_workflow",
    "wikipedia": "prudentia_wikipedia_web_workflow",
    "googlenews": "prudentia_googlenews_web_workflow",
    "google news": "prudentia_googlenews_web_workflow",
}


def _keyword_match_browser_workflow(
    intent: str, available: list[dict]
) -> dict | None:
    """Deterministic keyword fallback for browser workflows."""
    intent_lower = intent.lower()
    id_index = {w["id"]: w for w in available}
    for keyword, wf_id in _PRUDENTIA_KEYWORD_MAP.items():
        if keyword in intent_lower and wf_id in id_index:
            entry = id_index[wf_id]
            if entry.get("workflow"):
                return entry["workflow"]
            if entry.get("link"):
                try:
                    return requests.get(entry["link"], timeout=10).json()
                except Exception:
                    pass
            return {"id": wf_id}
    return None


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
        remote = [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "browser"
        ]
    except Exception:
        remote = []
    local = _load_local_browser_workflows()
    remote_ids = {w["id"] for w in remote}
    available = remote + [w for w in local if w.get("id") not in remote_ids]
    print(
        f"[BROWSER WF] workflow_source={workflow_source!r} "
        f"pinned_workflow_id={pinned_id!r} library_size={len(available)} "
        f"(remote={len(remote)}, local={len(local)})"
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
        if chosen_entry is None:
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
        if chosen_entry.get("link"):
            try:
                workflow = requests.get(chosen_entry["link"], timeout=10).json()
            except Exception:
                workflow = {"id": pinned_id}
        else:
            workflow = {"id": pinned_id}
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
        kw_wf = _keyword_match_browser_workflow(intent, available)
        if kw_wf:
            print(f"[BROWSER WF] LLM found no match; using keyword fallback")
            return {
                "workflow": kw_wf,
                "parameters": None,
                "reasoning": f"Keyword fallback matched workflow for intent: {intent!r}",
            }
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": result.reasoning,
        }

    chosen_entry = next((w for w in available if w["id"] == result.id), None)
    if chosen_entry and chosen_entry.get("workflow"):
        workflow = chosen_entry["workflow"]
        workflow.setdefault("id", chosen_entry["id"])
    elif chosen_entry and chosen_entry.get("link"):
        try:
            workflow = requests.get(chosen_entry["link"], timeout=10).json()
        except Exception:
            workflow = {}
    else:
        workflow = {}

    if not workflow:
        kw_wf = _keyword_match_browser_workflow(intent, available)
        if kw_wf:
            print(f"[BROWSER WF] link fetch failed; using keyword fallback")
            return {
                "workflow": kw_wf,
                "parameters": result.parameters,
                "reasoning": result.reasoning,
            }

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
