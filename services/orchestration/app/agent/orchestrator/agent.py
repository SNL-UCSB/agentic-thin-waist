from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from app.agent.browser.agent import (
    BrowserWorkflowContext,
)
from app.agent.browser.agent import (
    create_agent as create_browser_agent,
)
from app.agent.orchestrator.prompts import (
    PARSE_INTENT_PROMPT,
    build_examples_block,
)
from app.agent.orchestrator.schemas import ParsedIntent
from app.agent.shell.agent import ShellWorkflowContext
from app.agent.shell.agent import create_agent as create_shell_agent
from app.agent.utils import (
    get_model,
    log_claude_step,
    save_state,
    with_structured_output,
)
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.orchestration_manager import OrchestrationManager
from app.models.schemas import OrchestrationStatus

load_dotenv()


class OrchestratorState(MessagesState):
    intent: str
    orchestration_id: str
    workflow: dict[str, Any]
    workflow_parameters: dict[str, Any] | None
    workflow_reasoning: str | None
    workflow_source: str
    workflow_id: str | None
    use_examples: bool
    max_parallel_workers: int
    parsed_intent: dict[str, Any] | None
    intent_overrides: dict[str, Any]
    experiments: list[dict[str, Any]]
    orchestration_result: dict[str, Any] | None
    reasoning_steps: list[dict[str, Any]]


class OrchestratorContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    generator: ExperimentGenerator
    orchestration_manager: Any


def parse_intent(state: OrchestratorState) -> dict[str, Any]:
    orchestration_id = state["orchestration_id"]
    intent = state["intent"]
    use_examples = state.get("use_examples", True)

    print(f"\n{'#' * 60}")
    print(f"[AGENT {orchestration_id}] Step 1/3: Parsing intent via Claude …")
    print(f"[AGENT {orchestration_id}]   intent: {intent!r}")
    print(f"[AGENT {orchestration_id}]   use_examples={use_examples}")
    print(f"{'#' * 60}")

    save_state(state, status=OrchestrationStatus.parsing)

    model = get_model()
    examples_block = build_examples_block() if use_examples else ""

    prompt_value = PARSE_INTENT_PROMPT.invoke(
        {
            "examples_block": examples_block,
            "intent": intent,
        }
    )
    log_claude_step(
        "parse_intent",
        orchestration_id=orchestration_id,
        prompt="\n\n".join(
            str(msg.content) for msg in prompt_value.messages if hasattr(msg, "content")
        ),
    )

    structured_model = with_structured_output(model, ParsedIntent)
    parsed: ParsedIntent = structured_model.invoke(prompt_value.messages)
    parsed_dict = parsed.model_dump()
    log_claude_step(
        "parse_intent",
        orchestration_id=orchestration_id,
        reasoning=parsed.reasoning,
        output=parsed_dict,
    )

    print(
        f"[AGENT {orchestration_id}] Intent parsed → "
        f"apps={parsed.applications}  capacities={parsed.capacities}  "
        f"cc={parsed.cc_algorithms}"
    )

    reasoning_step = {
        "step": 1,
        "action": "parse_intent",
        "input": {"intent": intent},
        "output": parsed_dict,
        "reasoning": parsed.reasoning,
    }

    reasoning_steps = list(state.get("reasoning_steps") or [])
    reasoning_steps.append(reasoning_step)

    return {
        "parsed_intent": parsed_dict,
        "reasoning_steps": reasoning_steps,
        "messages": [
            AIMessage(content=f"Parsed intent: {parsed.reasoning}"),
        ],
    }


def generate_experiments(
    state: OrchestratorState, runtime: Runtime[OrchestratorContext]
) -> dict[str, Any]:
    orchestration_id = state["orchestration_id"]
    parsed = state.get("parsed_intent")  # Parsed Intent

    print(f"\n{'#' * 60}")
    print(f"[AGENT {orchestration_id}] Step 2/3: Generating experiment specs …")
    print(f"{'#' * 60}")

    save_state(state, status=OrchestrationStatus.generating)

    # Parsed Failed
    if not parsed:
        print(f"[AGENT {orchestration_id}] No parsed intent — skipping generation")
        return {
            "experiments": [],
            "messages": [AIMessage(content="No parsed intent available.")],
        }

    # Deterministic overrides from the request take precedence over LLM
    # extraction — this is how callers pin parameter sweeps or queue-size
    # studies without trusting the parser to interpret numbers correctly.
    # IMPORTANT: the merged dict must be written back into state because
    # the downstream ``execute_experiments`` node re-runs the generator with
    # ``state["parsed_intent"]`` (the orchestrator manager regenerates specs
    # rather than reusing the ones returned here). If we only merged locally
    # the overrides would silently disappear at that re-generation.
    overrides = state.get("intent_overrides") or {}
    if overrides:
        print(
            f"[AGENT {orchestration_id}] Applying intent_overrides: "
            f"{sorted(overrides.keys())}"
        )
        parsed = {**parsed, **overrides}

    generator = runtime.context.generator
    experiments = generator.generate(parsed)
    experiment_dicts = [e.model_dump() for e in experiments]

    for i, e in enumerate(experiments):
        print(
            f"[AGENT {orchestration_id}]   spec[{i}] id={e.experiment_id}  "
            f"capacity={e.capacity_mbps} Mbps  "
            f"latency={e.latency_ms} ms  cc={e.cc_algorithm}"
        )

    return {
        "experiments": experiment_dicts,
        # Persist the merged dict so ``execute_experiments`` → ``OrchestrationManager.run``
        # regenerates specs from the override-aware values, not the LLM-only ones.
        "parsed_intent": parsed,
        "messages": [
            AIMessage(content=f"Generated {len(experiments)} experiment(s)."),
        ],
    }


def route_workflow(state: OrchestratorState) -> str:
    """Route to shell or browser workflow node based on parsed application_type."""
    parsed = state.get("parsed_intent") or {}
    app_type = parsed.get("application_type", "shell")
    if app_type == "browser":
        return "browser_workflow"
    return "shell_workflow"


def shell_workflow(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the shell workflow generation agent."""
    orchestration_id = state["orchestration_id"]
    existing = state.get("workflow") or {}
    if existing:
        print(f"[AGENT {orchestration_id}] Routing → shell workflow (user-provided)")
        return {"workflow": existing}

    print(f"[AGENT {orchestration_id}] Routing → shell workflow agent")
    from main import NetGent

    agent = create_shell_agent()
    result = agent.invoke(
        {
            "intent": state["intent"],
            "workflow": {},
            "chosen_workflow": None,
            "parameters": None,
            "reasoning": "",
            "messages": [],
            "workflow_source": state.get("workflow_source") or "auto",
            "workflow_id": state.get("workflow_id"),
        },
        context=ShellWorkflowContext(
            netgent=NetGent(
                cdp_url=os.environ.get("BROWSERLESS_WS_ENDPOINT", "").strip() or None,
                headless=True,
            )
        ),
    )
    # Shell workflow parameter mapping is centralized in shell/agent.py.
    # Do not override with parse_intent workflow_parameters.
    selected_params = result.get("parameters")
    return {
        "workflow": result.get("workflow") or {},
        "workflow_parameters": selected_params,
        "workflow_reasoning": result.get("reasoning"),
    }


def browser_workflow(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the browser workflow generation agent."""
    orchestration_id = state["orchestration_id"]
    existing = state.get("workflow") or {}
    if existing:
        print(f"[AGENT {orchestration_id}] Routing → browser workflow (user-provided)")
        return {"workflow": existing}

    print(f"[AGENT {orchestration_id}] Routing → browser workflow agent")
    from main import NetGent

    agent = create_browser_agent()
    result = agent.invoke(
        {
            "intent": state["intent"],
            "workflow": {},
            "chosen_workflow": None,
            "parameters": None,
            "reasoning": "",
            "messages": [],
            "workflow_source": state.get("workflow_source") or "auto",
            "workflow_id": state.get("workflow_id"),
        },
        context=BrowserWorkflowContext(
            netgent=NetGent(
                cdp_url=os.environ.get("BROWSERLESS_WS_ENDPOINT", "").strip() or None,
                headless=True,
            )
        ),
    )
    return {
        "workflow": result.get("workflow") or {},
        "workflow_parameters": result.get("parameters"),
        "workflow_reasoning": result.get("reasoning"),
    }


def route_has_workflow(state: OrchestratorState) -> str:
    """Fail if no workflow was generated, otherwise proceed to execution."""
    workflow = state.get("workflow") or {}
    if workflow:
        return "execute_experiments"
    return "fail_no_workflow"


def fail_no_workflow(state: OrchestratorState) -> dict[str, Any]:
    """Halt the pipeline — no workflow was produced."""
    orchestration_id = state["orchestration_id"]
    reasoning = state.get("workflow_reasoning") or "No matching workflow found."
    print(f"[AGENT {orchestration_id}] FAILED — no workflow generated: {reasoning}")
    save_state(state, status=OrchestrationStatus.failed)
    return {
        "orchestration_result": {
            "status": "failed",
            "error": f"No workflow was generated by the workflow agent: {reasoning}",
        },
        "messages": [
            AIMessage(
                content=f"Failed: no workflow was generated. Reason: {reasoning}"
            ),
        ],
    }


def execute_experiments(
    state: OrchestratorState, runtime: Runtime[OrchestratorContext]
) -> dict[str, Any]:
    """Dispatch experiments via OrchestrationManager (workers, CTP, capture, workflow)."""
    orchestration_id = state["orchestration_id"]
    parsed = state.get("parsed_intent")
    experiments = state.get("experiments") or []
    intent = state.get("intent", "")
    max_parallel = state.get("max_parallel_workers", 1)

    print(f"\n{'#' * 60}")
    print(f"[AGENT {orchestration_id}] Step 3/3: Running OrchestrationManager …")
    print(f"[AGENT {orchestration_id}]   max_parallel_workers={max_parallel}")
    print(f"{'#' * 60}")

    save_state(state, status=OrchestrationStatus.executing)

    if not parsed or not experiments:
        print(f"[AGENT {orchestration_id}] No experiments to execute — skipping")
        return {
            "orchestration_result": {"status": "skipped", "reason": "no experiments"},
            "messages": [AIMessage(content="No experiments to execute.")],
        }

    workflow = state.get("workflow") or {}
    workflow_parameters = state.get("workflow_parameters")
    mgr = runtime.context.orchestration_manager
    result = mgr.run(
        orchestration_id,
        intent,
        parsed,
        workflow=workflow,
        workflow_parameters=workflow_parameters,
    )

    summary = result.get("summary", {})
    status = result.get("status", "unknown")
    total = summary.get("total_experiments", 0)
    successful = summary.get("successful", 0)
    failed = summary.get("failed", 0)

    print(
        f"[AGENT {orchestration_id}] Execution done: {successful}/{total} succeeded  "
        f"status={status}"
    )

    reasoning_step = {
        "step": 2,
        "action": "run_orchestration_manager",
        "input": {"intent": intent},
        "output": summary,
        "reasoning": "Connectivity-centric dispatch via OrchestrationManager.",
    }
    reasoning_steps = list(state.get("reasoning_steps") or [])
    reasoning_steps.append(reasoning_step)
    print(f"[AGENT {orchestration_id}] Multi-step reasoning trace:")
    for step in reasoning_steps:
        print(
            f"[AGENT {orchestration_id}]   step={step.get('step')} "
            f"action={step.get('action')} reasoning={step.get('reasoning')}"
        )

    final_status = (
        OrchestrationStatus.complete
        if status == "complete"
        else OrchestrationStatus.failed
    )

    save_state(
        state,
        status=final_status,
        experiments=result.get("experiment_specs", experiments),
        results=result.get("results", []),
    )

    result_lines = [
        f"Orchestration **{status}** (id: {orchestration_id})",
        f"  Total: {total}, Successful: {successful}, Failed: {failed}",
    ]
    for r in result.get("results", []):
        exp_id = r.get("experiment_id", "unknown")
        exp_status = r.get("status", "unknown")
        worker = r.get("worker_id", "N/A")
        error = r.get("error")
        line = f"  - {exp_id}: {exp_status} (worker: {worker})"
        if error:
            line += f" — {error}"
        result_lines.append(line)

    return {
        "orchestration_result": result,
        "reasoning_steps": reasoning_steps,
        "messages": [AIMessage(content="\n".join(result_lines))],
    }


def respond(state: OrchestratorState) -> dict[str, Any]:
    """Produce a final human-readable response summarizing the orchestration."""
    parsed = state.get("parsed_intent") or {}
    experiments = state.get("experiments") or []
    orch_result = state.get("orchestration_result") or {}
    clarifications = parsed.get("clarification_needed") or []

    parts = []
    if parsed.get("reasoning"):
        parts.append(f"**Reasoning:** {parsed['reasoning']}")

    if clarifications:
        parts.append("**Clarifications needed:**")
        for c in clarifications:
            parts.append(f"  - {c}")

    if experiments:
        parts.append(f"\n**{len(experiments)} experiment(s) generated.**")
    else:
        parts.append("\nNo experiments were generated.")

    summary = orch_result.get("summary")
    if summary:
        parts.append(
            f"\n**Execution complete:** "
            f"{summary.get('successful', 0)}/{summary.get('total_experiments', 0)} succeeded."
        )

    return {
        "messages": [AIMessage(content="\n".join(parts))],
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def create_agent():
    """Build and compile the orchestrator LangGraph agent."""
    graph = StateGraph(
        state_schema=OrchestratorState, context_schema=OrchestratorContext
    )

    graph.add_node("parse_intent", parse_intent)
    graph.add_node("generate_experiments", generate_experiments)
    graph.add_node("shell_workflow", shell_workflow)
    graph.add_node("browser_workflow", browser_workflow)
    graph.add_node("fail_no_workflow", fail_no_workflow)
    graph.add_node("execute_experiments", execute_experiments)
    graph.add_node("respond", respond)

    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "generate_experiments")
    graph.add_conditional_edges(
        "generate_experiments",
        route_workflow,
        {"shell_workflow": "shell_workflow", "browser_workflow": "browser_workflow"},
    )
    graph.add_conditional_edges(
        "shell_workflow",
        route_has_workflow,
        {
            "execute_experiments": "execute_experiments",
            "fail_no_workflow": "fail_no_workflow",
        },
    )
    graph.add_conditional_edges(
        "browser_workflow",
        route_has_workflow,
        {
            "execute_experiments": "execute_experiments",
            "fail_no_workflow": "fail_no_workflow",
        },
    )
    graph.add_edge("fail_no_workflow", "respond")
    graph.add_edge("execute_experiments", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


class OrchestratorAgent:
    """High-level wrapper around the LangGraph orchestrator agent."""

    def __init__(self) -> None:
        self.graph = create_agent()

    def run(
        self,
        orchestration_id: str,
        intent: str,
        workflow: dict[str, Any],
        *,
        use_examples: bool = True,
        max_parallel_workers: int = 1,
        workflow_source: str = "auto",
        workflow_id: str | None = None,
        intent_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the full orchestration pipeline for a given intent.

        Args:
            orchestration_id: Unique ID for this orchestration run.
            intent: Natural language research intent.
            workflow: NetGent workflow dict (state-machine JSON) to execute.
            use_examples: Whether to include few-shot examples in the prompt.
            max_parallel_workers: Max concurrent substrate workers.

        Returns:
            Dict with parsed_intent, experiments, orchestration_result,
            and reasoning_steps.
        """
        result = self.graph.invoke(
            {
                "intent": intent,
                "orchestration_id": orchestration_id,
                "workflow": workflow,
                "workflow_parameters": None,
                "workflow_reasoning": None,
                "workflow_source": workflow_source,
                "workflow_id": workflow_id,
                "use_examples": use_examples,
                "max_parallel_workers": max_parallel_workers,
                "messages": [HumanMessage(content=intent)],
                "parsed_intent": None,
                "intent_overrides": intent_overrides or {},
                "experiments": [],
                "orchestration_result": None,
                "reasoning_steps": [],
            },
            context={
                "generator": ExperimentGenerator(),
                "orchestration_manager": OrchestrationManager(
                    max_parallel_workers=max_parallel_workers,
                ),
            },
        )

        return {
            "parsed_intent": result.get("parsed_intent"),
            "experiments": result.get("experiments", []),
            "orchestration_result": result.get("orchestration_result"),
            "reasoning_steps": result.get("reasoning_steps", []),
        }
