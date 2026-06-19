"""Intent + OpenClaw endpoints and orchestration execution pipeline (Steps 8-10).

The ``process_intent`` background task delegates to the LangGraph-based
OrchestratorAgent which runs:

    parse_intent → generate_experiments → execute_experiments → respond
"""

import os
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.engine.orchestration_store import (
    load_orchestration,
    save_orchestration,
    load_orchestration_async,
    save_orchestration_async,
)
from app.agent.orchestrator import OrchestratorAgent
from app.models.schemas import (
    ResearchIntent,
    OrchestrationResponse,
    OrchestrationProgress,
    OrchestrationStatus,
)
from app.engine.tools import load_tools
from app.engine.skills import load_skills, SkillExecutor

router = APIRouter()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _build_detailed_progress(orch: dict) -> dict:
    """Build compact, UI-friendly detail flags from lifecycle + iteration phases."""
    lifecycle_stages = orch.get("lifecycle_stages", []) or []
    results = orch.get("results", []) or []

    stage_names = {
        str(s.get("stage", "")).strip().lower()
        for s in lifecycle_stages
        if isinstance(s, dict)
    }
    phase_names = set()
    for item in results:
        phases = ((item or {}).get("lifecycle") or {}).get("phases", [])
        for phase in phases:
            if isinstance(phase, dict) and phase.get("phase"):
                phase_names.add(str(phase["phase"]).strip().lower())

    phase_counts: dict[str, int] = {}
    for item in results:
        phases = ((item or {}).get("lifecycle") or {}).get("phases", [])
        seen = set()
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            name = str(phase.get("phase", "")).strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            phase_counts[name] = phase_counts.get(name, 0) + 1

    total_iterations = len(results)
    return {
        "stage_flags": {
            "received_intent": "received_intent" in stage_names,
            "generated_experiment_spec": "generated_experiment_spec" in stage_names,
            "validating_ctp_service": "validating_ctp_service" in stage_names,
            "ctp_replay_ready": "ctp_replay_ready" in stage_names,
            "application_supported": "application_supported" in stage_names,
            "worker_available": "worker_available" in stage_names,
            "starting_iteration": "starting_iteration" in stage_names,
            "telemetry_save_complete": "telemetry_save_complete" in stage_names,
            "iteration_succeeded": "iteration_succeeded" in stage_names,
            "iteration_failed": "iteration_failed" in stage_names,
            "experiment_succeeded": "experiment_succeeded" in stage_names,
            "experiment_failed": "experiment_failed" in stage_names,
        },
        "iteration_phase_flags": {
            "ctp_validation_start": "ctp_validation_start" in phase_names,
            "ctp_validation_done": "ctp_validation_done" in phase_names,
            "registered": "registered" in phase_names,
            "dispatch_done": "dispatch_done" in phase_names,
            "collecting": "collecting" in phase_names,
            "complete": "complete" in phase_names,
            "failed": "failed" in phase_names,
            "netgent_execution_skipped": "netgent_execution_skipped" in phase_names,
        },
        "iteration_phase_completion": (
            {
                "ctp_validation_done": {
                    "completed_iterations": phase_counts.get("ctp_validation_done", 0),
                    "total_iterations": total_iterations,
                },
                "complete": {
                    "completed_iterations": phase_counts.get("complete", 0),
                    "total_iterations": total_iterations,
                },
                "failed": {
                    "completed_iterations": phase_counts.get("failed", 0),
                    "total_iterations": total_iterations,
                },
            }
        ),
    }


@router.post("/intent", response_model=OrchestrationResponse, status_code=202)
async def submit_intent(request: ResearchIntent, background_tasks: BackgroundTasks):
    orch_id = f"orch-{uuid.uuid4().hex[:8]}"
    record = {
        "orchestration_id": orch_id,
        "intent": request.intent,
        "status": OrchestrationStatus.pending,
        "experiments": [],
        "reasoning_steps": [],
        "results": [],
    }
    try:
        await save_orchestration_async(record)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Orchestration persistence unavailable: {exc}",
        ) from exc

    background_tasks.add_task(process_intent, orch_id, request)

    return OrchestrationResponse(
        orchestration_id=orch_id,
        status=OrchestrationStatus.pending,
        intent=request.intent,
        generated_experiments=0,
    )


def process_intent(orch_id: str, request: ResearchIntent) -> None:
    """Background task: run the full pipeline via the LangGraph OrchestratorAgent.

    The agent graph handles parsing, experiment generation, execution, and
    orchestration-store persistence internally.
    """
    orch = load_orchestration(orch_id)
    if orch is None:
        print(f"[INTENT {orch_id}] ERROR: orchestration record not found in store")
        return

    try:
        use_examples = bool(request.preferences.get("use_examples", True))
        max_parallel = int(request.preferences.get("max_parallel_workers", 1))

        default_source = (
            os.environ.get("ORCH_DEFAULT_WORKFLOW_SOURCE", "auto").strip().lower()
            or "auto"
        )
        if default_source not in {"auto", "library", "generate"}:
            default_source = "auto"
        workflow_source = request.workflow_source or default_source
        workflow_id = request.workflow_id

        print(f"\n{'#'*60}")
        print(f"[INTENT {orch_id}] Running LangGraph OrchestratorAgent …")
        print(f"[INTENT {orch_id}]   intent: {request.intent!r}")
        print(f"[INTENT {orch_id}]   use_examples={use_examples}")
        print(f"[INTENT {orch_id}]   max_parallel_workers={max_parallel}")
        print(
            f"[INTENT {orch_id}]   workflow_source={workflow_source!r} "
            f"workflow_id={workflow_id!r}"
        )
        bypass_llm = _parse_bool(
            request.preferences.get("bypass_llm"),
            _env_flag("ORCH_BYPASS_LLM", False),
        )
        print(f"[INTENT {orch_id}]   bypass_llm={bypass_llm}")
        print(f"{'#'*60}")

        workflow = request.context.get("workflow") or {}

        # Deterministic overrides from request.context: these win over whatever
        # the LLM extracts from the intent text. Use for parameters you want to
        # set programmatically (parameter sweeps, queue-size studies, ...).
        intent_overrides: dict = {}
        for key in (
            "capacities",
            "latencies",
            "cc_algorithms",
            "aqm_policy",
            "buffer_packets",
            "qdisc_params",
            "duration_seconds",
            "num_trials",
            "ctp_name",
            "ctp_list",
            "fake_media",
            "applications",
            "application_type",
            "workflow_parameters",
            "upload_mbps",
            "ctp_cluster",
            "ctp_capacity_range",
        ):
            if key in request.context and request.context[key] is not None:
                intent_overrides[key] = request.context[key]

        agent = OrchestratorAgent()
        result = agent.run(
            orch_id,
            request.intent,
            workflow,
            use_examples=use_examples,
            max_parallel_workers=max_parallel,
            workflow_source=workflow_source,
            workflow_id=workflow_id,
            intent_overrides=intent_overrides,
            bypass_llm=bypass_llm,
            context=request.context,
        )

        orch_result = result.get("orchestration_result") or {}
        final_status = orch_result.get("status", "failed")
        if final_status == "complete":
            final_status = OrchestrationStatus.complete
        else:
            final_status = OrchestrationStatus.failed

        orch["status"] = final_status
        orch["experiments"] = result.get("experiments", [])
        orch["results"] = orch_result.get("results", [])
        orch["reasoning_steps"] = result.get("reasoning_steps", [])
        if orch_result.get("error"):
            orch["error"] = orch_result["error"]
        save_orchestration(orch)

        summary = orch_result.get("summary", {})
        print(
            f"\n[INTENT {orch_id}] DONE — final status={final_status}  "
            f"summary={summary}"
        )

    except Exception as e:
        orch["status"] = OrchestrationStatus.failed
        orch["error"] = str(e)
        print(f"[INTENT {orch_id}] EXCEPTION: {e}")
        try:
            save_orchestration(orch)
        except Exception:
            pass


@router.get("/tools")
async def get_tools():
    tools = load_tools()
    return {"tools": tools}


@router.get("/skills")
async def get_skills():
    skills = load_skills()
    return {"skills": skills}


@router.post("/skills/{skill_name}/execute")
async def execute_skill(skill_name: str, payload: dict):
    executor = SkillExecutor()
    if skill_name == "parameter_sweep":
        out = executor.execute_parameter_sweep(payload)
    elif skill_name == "application_comparison":
        out = executor.execute_application_comparison(payload)
    elif skill_name == "baseline_establishment":
        out = executor.execute_baseline(payload)
    elif skill_name == "network_characterization":
        out = executor.execute_network_characterization(payload)
    elif skill_name == "replicate_study":
        out = executor.execute_replicate_study(payload)
    else:
        raise HTTPException(status_code=404, detail=f"Unknown skill '{skill_name}'")
    return {"skill": skill_name, "generated_experiments": [e.model_dump() for e in out]}


@router.get("/orchestration/{orch_id}")
async def get_status(orch_id: str):
    orch = await load_orchestration_async(orch_id)
    if orch is None:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": orch["orchestration_id"],
        "status": orch["status"],
        "error": orch.get("error"),
        "generated_experiments": orch.get("experiments", []),
        "lifecycle_stages": orch.get("lifecycle_stages", []),
        "detailed_progress": _build_detailed_progress(orch),
        "preflight": orch.get("preflight"),
        "netgent_execution": orch.get("netgent_execution"),
    }


@router.get("/orchestration/{orch_id}/results")
async def get_results(orch_id: str):
    orch = await load_orchestration_async(orch_id)
    if orch is None:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": orch["orchestration_id"],
        "status": orch["status"],
        "results": orch.get("results", []),
        "lifecycle_stages": orch.get("lifecycle_stages", []),
        "preflight": orch.get("preflight"),
        "netgent_execution": orch.get("netgent_execution"),
    }


@router.get("/orchestration/{orch_id}/reasoning")
async def get_reasoning(orch_id: str):
    orch = await load_orchestration_async(orch_id)
    if orch is None:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": orch["orchestration_id"],
        "reasoning_steps": orch["reasoning_steps"],
    }
