from __future__ import annotations

import json
import pathlib
import re
from typing import TYPE_CHECKING, Any

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.utils import get_model, log_claude_step, with_structured_output
from core.config import settings as _netgent_settings


def get_netgent_llm_provider() -> str:
    return _netgent_settings.NETGENT_LLM_PROVIDER


def netgent_has_llm_credentials(provider: str) -> bool:
    if provider == "anthropic":
        return bool(_netgent_settings.ANTHROPIC_API_KEY)
    return bool(_netgent_settings.GOOGLE_API_KEY)


if TYPE_CHECKING:
    from main import NetGent

WORKFLOW_INDEX_URL = "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows/index.json"
_SCHEMAS_PATH = (
    pathlib.Path(__file__).parent.parent.parent / "config" / "workflow_schemas.json"
)
_WORKFLOW_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = (
    json.loads(_SCHEMAS_PATH.read_text()) if _SCHEMAS_PATH.exists() else {}
)
# Local shell workflows bundled with the orchestrator. Each entry follows the
# same shape as the remote netgent-workflow library plus an optional inline
# "workflow" field so we don't have to fetch the spec over HTTP.
_LOCAL_SHELL_WORKFLOWS_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "config"
    / "local_shell_workflows.json"
)
_LOCAL_SHELL_WORKFLOWS: list[dict[str, Any]] = (
    json.loads(_LOCAL_SHELL_WORKFLOWS_PATH.read_text())
    if _LOCAL_SHELL_WORKFLOWS_PATH.exists()
    else []
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
_DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")


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


def _load_shell_workflows() -> list[dict[str, Any]]:
    """Return shell workflows from the remote library, merged with local ones.

    Local entries take precedence over remote ones with the same id so the
    orchestrator can ship a workflow without round-tripping to GitHub.
    """
    remote: list[dict[str, Any]] = []
    try:
        remote = [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "shell"
        ]
    except Exception:
        remote = []

    local_ids = {w.get("id") for w in _LOCAL_SHELL_WORKFLOWS if w.get("id")}
    merged = [w for w in remote if w.get("id") not in local_ids]
    merged.extend(_LOCAL_SHELL_WORKFLOWS)
    return merged


def _default_params_for_workflow(workflow_id: str) -> dict[str, Any] | None:
    schema = _WORKFLOW_SCHEMAS.get(workflow_id) or {}
    if not schema:
        return None
    return {
        key: meta.get("default") for key, meta in schema.items() if "default" in meta
    } or None


class ShellWorkflowGenerationState(MessagesState):
    intent: str
    workflow: dict[str, Any]
    chosen_workflow: dict[str, Any] | None
    parameters: dict[str, Any] | None
    reasoning: str
    workflow_source: str
    workflow_id: str | None


class ShellWorkflowContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    netgent: NetGent


class ChooseWorkflow(BaseModel):
    is_valid: bool
    reasoning: str
    id: str | None = None
    parameters: dict[str, Any] | None = None


class MapWorkflowParams(BaseModel):
    parameters: dict[str, Any] | None = None
    reasoning: str


def _extract_explicit_host_from_intent(intent: str) -> str | None:
    ip_match = _IPV4_RE.search(intent)
    if ip_match:
        return ip_match.group(0)
    domain_match = _DOMAIN_RE.search(intent)
    if domain_match:
        return domain_match.group(0)
    return None


def _apply_intent_param_overrides(
    intent: str, parameters: dict[str, Any] | None, param_names: list[str]
) -> dict[str, Any] | None:
    params = dict(parameters or {})
    if not params:
        return parameters
    if "host" in param_names:
        explicit_host = _extract_explicit_host_from_intent(intent)
        if explicit_host:
            params["host"] = explicit_host
    return params


def _validate_mapped_params(
    parameters: dict[str, Any] | None,
    param_names: list[str],
    schema: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    params = parameters or {}
    if not param_names:
        return None

    missing = [name for name in param_names if name not in params]
    extra = [name for name in params if name not in param_names]
    if missing or extra:
        raise ValueError(
            f"invalid mapped parameters; missing={missing} extra={extra} "
            f"allowed={param_names}"
        )

    for key, meta in schema.items():
        if key not in params:
            continue
        if meta.get("type") == "boolean":
            value = params[key]
            if isinstance(value, bool):
                continue
            if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
                continue
            raise ValueError(
                f"boolean parameter {key!r} must be true/false, got {value!r}"
            )
    return params


def _map_workflow_params_with_claude(
    intent: str,
    workflow_id: str,
    param_names: list[str],
    workflow_schema: dict[str, dict[str, Any]],
    workflow_description: str,
) -> tuple[dict[str, Any] | None, str]:
    prompt = [
        HumanMessage(
            content=(
                "Map an experiment intent to workflow runtime parameters.\n\n"
                f"Intent: {intent}\n"
                f"Workflow id: {workflow_id}\n"
                f"Workflow description: {workflow_description}\n"
                f"Allowed parameter names: {param_names}\n"
                f"Parameter schema: {json.dumps(workflow_schema)}\n\n"
                "Rules:\n"
                "- Output parameters for runtime substitution.\n"
                "- Include every allowed parameter exactly once.\n"
                "- Do not output unknown keys.\n"
                "- Respect schema types and defaults.\n"
                "- For booleans, output exactly true or false.\n"
            )
        )
    ]
    log_claude_step(
        "shell_map_workflow_params",
        prompt="\n\n".join(
            str(msg.content) for msg in prompt if hasattr(msg, "content")
        ),
    )
    model = get_model()
    result: MapWorkflowParams = with_structured_output(model, MapWorkflowParams).invoke(
        prompt
    )
    log_claude_step(
        "shell_map_workflow_params",
        reasoning=result.reasoning,
        output=result.model_dump(),
    )
    mapped = _apply_intent_param_overrides(intent, result.parameters, param_names)
    mapped = _validate_mapped_params(mapped, param_names, workflow_schema)
    return mapped, result.reasoning


def _pin_shell_workflow(
    intent: str,
    selected_id: str,
    available: list[dict[str, Any]],
    source_label: str,
) -> dict[str, Any]:
    """Fetch a library workflow by id, run the parameter mapper, return state delta.

    `source_label` is included in the reasoning string for trace clarity
    (e.g. "request workflow_id", "library selection").
    """
    chosen_entry = next((w for w in available if w.get("id") == selected_id), None)
    if not chosen_entry:
        reasoning = (
            f"Requested workflow id {selected_id!r} not present in the shell "
            f"workflow library."
        )
        print(f"[SHELL WF] pin failed: {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
            "chosen_workflow": {
                "is_valid": False,
                "reasoning": reasoning,
                "id": selected_id,
                "parameters": None,
                "fail_fast": True,
            },
        }

    inline_workflow = chosen_entry.get("workflow")
    if isinstance(inline_workflow, dict) and inline_workflow:
        workflow = dict(inline_workflow)
    elif chosen_entry.get("link"):
        try:
            workflow = requests.get(chosen_entry["link"], timeout=10).json()
        except Exception:
            workflow = {"id": selected_id}
    else:
        workflow = {"id": selected_id}
    workflow.setdefault("id", selected_id)

    schema = _WORKFLOW_SCHEMAS.get(selected_id, {})
    param_names = list(chosen_entry.get("parameters") or list(schema.keys()))
    try:
        parameters, map_reasoning = _map_workflow_params_with_claude(
            intent=intent,
            workflow_id=selected_id,
            param_names=param_names,
            workflow_schema=schema,
            workflow_description=str(chosen_entry.get("description", "")),
        )
    except Exception as exc:
        reasoning = (
            f"Selected shell workflow {selected_id!r} via {source_label}, "
            f"but parameter mapper failed: {exc}"
        )
        print(f"[SHELL WF] mapper failure: {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
            "chosen_workflow": {
                "is_valid": False,
                "reasoning": reasoning,
                "id": selected_id,
                "parameters": None,
                "fail_fast": True,
            },
        }
    print(
        f"[SHELL WF] pinned id={selected_id!r} source={source_label} "
        f"workflow_param_source=claude_mapper params={parameters}"
    )
    reasoning = (
        f"Selected shell workflow {selected_id!r} via {source_label}. "
        f"Mapper reasoning: {map_reasoning}"
    )
    return {
        "workflow": workflow,
        "parameters": parameters,
        "reasoning": reasoning,
        "chosen_workflow": {
            "is_valid": True,
            "reasoning": reasoning,
            "id": selected_id,
            "parameters": parameters,
        },
    }


def choose_workflow(
    state: ShellWorkflowGenerationState, runtime: Runtime[ShellWorkflowContext]
) -> dict[str, Any]:
    """Pick a shell workflow per `workflow_source` and `workflow_id`.

    Modes:
    - `auto` (default): LLM picks from the library; if no match, fall through to
      generation (the orchestrator graph routes invalid + no-fail_fast → generate).
    - `library`: LLM picks from the library only; fail loudly on no match.
    - `generate`: skip the library, route directly to the generate node.

    `workflow_id`, when set, pins selection and bypasses `workflow_source`.
    """
    intent = state["intent"]
    available = _load_shell_workflows()

    workflow_source = (state.get("workflow_source") or "auto").lower()
    if workflow_source not in {"auto", "library", "generate"}:
        workflow_source = "auto"
    pinned_id = (state.get("workflow_id") or "").strip() or None
    print(
        f"[SHELL WF] workflow_source={workflow_source!r} "
        f"pinned_workflow_id={pinned_id!r} "
        f"library_size={len(available)}"
    )

    # 1. Explicit id pin wins over workflow_source.
    if pinned_id:
        return _pin_shell_workflow(
            intent=intent,
            selected_id=pinned_id,
            available=available,
            source_label="request workflow_id",
        )

    # 2. Generate-only: short-circuit to the generate node via is_valid=False
    #    (no fail_fast → route_valid_workflow falls through to generate).
    if workflow_source == "generate":
        reasoning = (
            "workflow_source=generate — skipping the library and requesting "
            "workflow generation."
        )
        print(f"[SHELL WF] {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
            "chosen_workflow": {
                "is_valid": False,
                "reasoning": reasoning,
                "id": None,
                "parameters": None,
            },
        }

    # 3. auto / library: ask the LLM to pick from the library.
    if workflow_source == "library" and not available:
        reasoning = (
            "workflow_source=library but the shell workflow library is empty "
            "or unreachable."
        )
        print(f"[SHELL WF] {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
            "chosen_workflow": {
                "is_valid": False,
                "reasoning": reasoning,
                "id": None,
                "parameters": None,
                "fail_fast": True,
            },
        }

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
    # The structured picker is non-deterministic and occasionally returns
    # is_valid=False for intents that clearly match a library workflow
    # (observed: identical wget intents rejected against test_wget_workflow on
    # 4 of 15 sweep runs). Try twice before giving up; LLM temperature
    # variation typically resolves the flake without changing legitimate
    # "no match" verdicts (which stay False on both attempts).
    result: ChooseWorkflow | None = None
    for attempt in range(2):
        result = with_structured_output(model, ChooseWorkflow).invoke(prompt)
        print(
            f"[SHELL WF] LLM choose_workflow attempt={attempt + 1}/2: "
            f"is_valid={result.is_valid} id={result.id!r} "
            f"params={result.parameters}"
        )
        log_claude_step(
            "shell_choose_workflow",
            reasoning=result.reasoning,
            output=result.model_dump(),
        )
        if result.is_valid and result.id:
            break

    if result.is_valid and result.id:
        return _pin_shell_workflow(
            intent=intent,
            selected_id=result.id,
            available=available,
            source_label="library selection (LLM)",
        )

    # is_valid=False — branch on workflow_source.
    if workflow_source == "library":
        reasoning = (
            f"workflow_source=library and no library entry matched the intent. "
            f"Picker reasoning: {result.reasoning}"
        )
        print(f"[SHELL WF] {reasoning}")
        return {
            "workflow": {},
            "parameters": None,
            "reasoning": reasoning,
            "chosen_workflow": {
                "is_valid": False,
                "reasoning": reasoning,
                "id": None,
                "parameters": None,
                "fail_fast": True,
            },
        }

    # workflow_source == "auto" — let route_valid_workflow fall through to generate
    # (or fail cleanly if NetGent LLM creds are missing).
    netgent_provider = get_netgent_llm_provider()
    has_creds = netgent_has_llm_credentials(netgent_provider)
    reasoning = result.reasoning
    if not has_creds:
        reasoning = (
            f"{result.reasoning} No matching library workflow, and workflow "
            f"generation is unavailable because {netgent_provider} credentials "
            "are not configured."
        )
        print("[SHELL WF] No library match and no NetGent LLM creds; failing request")
    return {
        "workflow": {},
        "parameters": None,
        "reasoning": reasoning,
        "chosen_workflow": {
            "is_valid": False,
            "reasoning": reasoning,
            "id": result.id,
            "parameters": None,
        },
    }


def route_valid_workflow(state: ShellWorkflowGenerationState) -> str:
    """Route based on whether the chosen workflow is valid."""
    chosen = state.get("chosen_workflow")
    if chosen and chosen.get("is_valid"):
        print(
            f"[SHELL WF] route_valid_workflow: is_valid=True, id={chosen.get('id')!r}"
        )
        return "choose_workflow"
    if chosen and chosen.get("fail_fast"):
        print("[SHELL WF] route_valid_workflow: fail_fast=True, ending")
        return "choose_workflow"
    netgent_provider = get_netgent_llm_provider()
    has_creds = netgent_has_llm_credentials(netgent_provider)
    print(
        f"[SHELL WF] route_valid_workflow: is_valid=False, provider={netgent_provider} has_llm_creds={has_creds}"
    )
    if not has_creds:
        print("[SHELL WF] No NetGent LLM creds — ending with invalid/missing workflow")
        return "choose_workflow"
    return "generate"


def generate(
    state: ShellWorkflowGenerationState, runtime: Runtime[ShellWorkflowContext]
) -> dict[str, Any]:
    """Generate a shell workflow from the intent using the NetGent shell subagent."""
    from agents.subagents.shell.agent import (
        create_agent as create_shell_netgent_agent,
    )
    from engine.controller import ProgramController
    from engine.executor import StateExecutor
    from engine.runner import WorkflowRunner
    from registry.actions.network import NETWORK_ACTIONS
    from registry.triggers.base_action import always_true

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
