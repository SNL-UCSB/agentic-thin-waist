"""Intent + OpenClaw endpoints and orchestration execution pipeline (Steps 8-10)."""

import os
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.engine.executor import ToolRouter, ExecutionManager, DownstreamClients
from app.engine.orchestration_store import load_orchestration, save_orchestration
from app.engine.orchestration_workflow import run_orchestration
from app.models.schemas import (
    ResearchIntent,
    OrchestrationResponse,
    OrchestrationProgress,
    OrchestrationStatus,
)
from app.engine.intent_parser import IntentParser
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.claude_client import ClaudeClient
from app.engine.tools import load_tools
from app.engine.skills import load_skills, SkillExecutor

router = APIRouter()


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
        save_orchestration(record)
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
    """Background task: parse → generate → preflight → dispatch → aggregate.

    When ``preferences.run_immediately`` is set, the full orchestration
    workflow runs (preflight checks, per-iteration dispatch, telemetry
    persistence, aggregation).  Otherwise only parsing and generation are
    performed and the experiments are returned as planned-only.
    """
    orch = load_orchestration(orch_id)
    if orch is None:
        return
    try:
        execute_now = bool(request.preferences.get("run_immediately", False))
        use_examples = bool(request.preferences.get("use_examples", True))

        # 1. Parse intent
        orch["status"] = OrchestrationStatus.parsing
        save_orchestration(orch)
        claude = ClaudeClient()
        parser = IntentParser(claude)
        parsed = parser.parse(request.intent, use_examples=use_examples)
        orch["reasoning_steps"].append(
            {
                "step": 1,
                "action": "parse_intent",
                "input": {"intent": request.intent},
                "output": parsed,
                "reasoning": parsed.get("reasoning", ""),
            }
        )
        save_orchestration(orch)

        if execute_now:
            # Delegate to orchestration workflow runner (preflight + iterations + aggregation).
            result = run_orchestration(
                orch_id, request.intent, parsed,
                clients=DownstreamClients(),
            )
            # Workflow runner persists final state itself; reload to avoid
            # overwriting lifecycle_stages / preflight written by it.
            orch = load_orchestration(orch_id) or orch
            orch["reasoning_steps"].append(
                {
                    "step": 2,
                    "action": "run_orchestration_workflow",
                    "input": {"intent": request.intent},
                    "output": result.get("summary", {}),
                    "reasoning": "Full orchestration workflow via run_orchestration.",
                }
            )
            save_orchestration(orch)
        else:
            # Generate experiment specs only (no dispatch).
            orch["status"] = OrchestrationStatus.generating
            save_orchestration(orch)
            generator = ExperimentGenerator()
            experiments = generator.generate(parsed)
            experiment_payloads = [e.model_dump() for e in experiments]
            orch["experiments"] = experiment_payloads
            orch["results"] = [
                {
                    "status": "planned_only",
                    "message": "Set preferences.run_immediately=true to dispatch to downstream services.",
                    "planned_experiments": len(experiment_payloads),
                }
            ]
            orch["status"] = OrchestrationStatus.complete
            orch.pop("error", None)
            save_orchestration(orch)

    except Exception as e:
        orch["status"] = OrchestrationStatus.failed
        orch["error"] = str(e)
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
    orch = load_orchestration(orch_id)
    if orch is None:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": orch["orchestration_id"],
        "status": orch["status"],
        "generated_experiments": orch.get("experiments", []),
        "lifecycle_stages": orch.get("lifecycle_stages", []),
        "detailed_progress": _build_detailed_progress(orch),
        "preflight": orch.get("preflight"),
        "netgent_execution": orch.get("netgent_execution"),
    }


@router.get("/orchestration/{orch_id}/results")
async def get_results(orch_id: str):
    orch = load_orchestration(orch_id)
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
    orch = load_orchestration(orch_id)
    if orch is None:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": orch["orchestration_id"],
        "reasoning_steps": orch["reasoning_steps"],
    }
