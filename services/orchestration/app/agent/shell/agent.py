from __future__ import annotations

import json
import os
import pathlib
import re
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
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
_DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


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
    try:
        return [
            w
            for w in requests.get(WORKFLOW_INDEX_URL, timeout=10).json()
            if w.get("type") == "shell"
        ]
    except Exception:
        return []


def _infer_workflow_id_from_intent(
    intent: str, available: list[dict[str, Any]]
) -> str | None:
    lowered = intent.lower()
    keyword_to_ids = (
        ("ndt", ("test_ndt_workflow",)),
        ("iperf", ("test_iperf_workflow",)),
        ("ping", ("test_shell_workflow",)),
    )
    available_ids = {str(w.get("id")) for w in available}
    for keyword, candidates in keyword_to_ids:
        if keyword in lowered:
            for candidate in candidates:
                if candidate in available_ids:
                    return candidate
    return None


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
    result: MapWorkflowParams = model.with_structured_output(MapWorkflowParams).invoke(
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


def choose_workflow(
    state: ShellWorkflowGenerationState, runtime: Runtime[ShellWorkflowContext]
) -> dict[str, Any]:
    """Ask Claude to pick an existing NetGent shell workflow that fits the intent."""
    intent = state["intent"]
    available = _load_shell_workflows()
    force_existing = _env_truthy("ORCH_FORCE_EXISTING_WORKFLOW", default=False)
    forced_workflow_id = (os.getenv("ORCH_FORCE_WORKFLOW_ID") or "").strip() or None
    print(
        f"[SHELL WF] forced_mode={force_existing} forced_workflow_id={forced_workflow_id!r}"
    )

    if force_existing:
        selected_id = forced_workflow_id or _infer_workflow_id_from_intent(
            intent, available
        )
        source = "env override" if forced_workflow_id else "intent keyword"
        chosen_entry = next((w for w in available if w.get("id") == selected_id), None)
        if not selected_id or not chosen_entry:
            reasoning = (
                "Forced existing-workflow mode enabled, but no matching shell workflow "
                f"was found for intent and override={forced_workflow_id!r}."
            )
            print(f"[SHELL WF] forced selection failed: {reasoning}")
            return {
                "workflow": {},
                "parameters": None,
                "reasoning": reasoning,
                "chosen_workflow": {
                    "is_valid": False,
                    "reasoning": reasoning,
                    "id": selected_id,
                    "parameters": None,
                },
            }

        workflow: dict[str, Any]
        if chosen_entry.get("link"):
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
                f"Forced existing-workflow mode selected {selected_id!r}, but "
                f"workflow parameter mapper failed: {exc}"
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
            f"[SHELL WF] forced selection source={source} id={selected_id!r} "
            f"workflow_param_source=claude_mapper params={parameters}"
        )
        reasoning = (
            "Forced existing-workflow mode enabled; selected prebuilt shell workflow "
            f"{selected_id!r} via {source}. Mapper reasoning: {map_reasoning}"
        )
        chosen_workflow = {
            "is_valid": True,
            "reasoning": reasoning,
            "id": selected_id,
            "parameters": parameters,
        }
        return {
            "workflow": workflow,
            "parameters": parameters,
            "reasoning": reasoning,
            "chosen_workflow": chosen_workflow,
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

    parameters: dict[str, Any] | None = None
    chosen_payload = result.model_dump()
    if result.is_valid and result.id:
        schema = _WORKFLOW_SCHEMAS.get(result.id, {})
        param_names = list(
            (chosen_entry or {}).get("parameters") or list(schema.keys())
        )
        try:
            parameters, map_reasoning = _map_workflow_params_with_claude(
                intent=intent,
                workflow_id=result.id,
                param_names=param_names,
                workflow_schema=schema,
                workflow_description=str((chosen_entry or {}).get("description", "")),
            )
            chosen_payload["parameters"] = parameters
            print(
                "[SHELL WF] workflow_param_source=claude_mapper "
                f"id={result.id!r} params={parameters}"
            )
            reasoning = f"{reasoning} Mapper reasoning: {map_reasoning}"
        except Exception as exc:
            reasoning = (
                f"Workflow {result.id!r} selected, but workflow parameter mapper "
                f"failed: {exc}"
            )
            print(f"[SHELL WF] mapper failure: {reasoning}")
            workflow = {}
            chosen_payload = {
                "is_valid": False,
                "reasoning": reasoning,
                "id": result.id,
                "parameters": None,
                "fail_fast": True,
            }

    return {
        "workflow": workflow,
        "parameters": parameters,
        "reasoning": reasoning,
        "chosen_workflow": chosen_payload,
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
