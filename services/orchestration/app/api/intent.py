"""Intent-related API endpoints — POST /intent and status tracking (Step 8)."""

import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models.schemas import (
    ResearchIntent,
    OrchestrationResponse,
    OrchestrationProgress,
    OrchestrationStatus,
)
from app.engine.intent_parser import IntentParser
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.claude_client import ClaudeClient

router = APIRouter()

# In-memory store for orchestration requests (replace with DB later)
ORCHESTRATIONS: dict = {}


@router.post("/intent", response_model=OrchestrationResponse, status_code=202)
async def submit_intent(request: ResearchIntent, background_tasks: BackgroundTasks):
    orch_id = f"orch-{uuid.uuid4().hex[:8]}"
    ORCHESTRATIONS[orch_id] = {
        "orchestration_id": orch_id,
        "intent": request.intent,
        "status": OrchestrationStatus.pending,
        "experiments": [],
        "reasoning_steps": [],
        "results": [],
    }

    background_tasks.add_task(process_intent, orch_id, request)

    return OrchestrationResponse(
        orchestration_id=orch_id,
        status=OrchestrationStatus.pending,
        intent=request.intent,
        generated_experiments=0,
    )


def process_intent(orch_id: str, request: ResearchIntent) -> None:
    """Background task: parse → generate → validate → dispatch."""
    orch = ORCHESTRATIONS[orch_id]
    try:
        # Step 1: Parse
        orch["status"] = OrchestrationStatus.parsing
        claude = ClaudeClient()
        parser = IntentParser(claude)
        parsed = parser.parse(request.intent)

        # Step 2: Generate
        orch["status"] = OrchestrationStatus.generating
        generator = ExperimentGenerator()
        experiments = generator.generate(parsed)
        orch["experiments"] = [e.model_dump() for e in experiments]

        # Step 3: Validate (against CTP Service — stub for now)
        orch["status"] = OrchestrationStatus.validating

        # Step 4: Dispatch (to Experiment API — stub for now)
        orch["status"] = OrchestrationStatus.executing

        # Mark complete
        orch["status"] = OrchestrationStatus.complete

    except Exception as e:
        orch["status"] = OrchestrationStatus.failed
        orch["error"] = str(e)


@router.get("/orchestration/{orch_id}", response_model=OrchestrationProgress)
async def get_status(orch_id: str) -> OrchestrationProgress:
    if orch_id not in ORCHESTRATIONS:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    orch = ORCHESTRATIONS[orch_id]
    return OrchestrationProgress(
        orchestration_id=orch["orchestration_id"],
        status=orch["status"],
        progress={},
        generated_experiments=orch["experiments"],
    )


@router.get("/orchestration/{orch_id}/results")
async def get_results(orch_id: str):
    if orch_id not in ORCHESTRATIONS:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    orch = ORCHESTRATIONS[orch_id]
    return {
        "orchestration_id": orch["orchestration_id"],
        "status": orch["status"],
        "results": orch["results"],
    }


@router.get("/orchestration/{orch_id}/reasoning")
async def get_reasoning(orch_id: str):
    if orch_id not in ORCHESTRATIONS:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    orch = ORCHESTRATIONS[orch_id]
    return {
        "orchestration_id": orch["orchestration_id"],
        "reasoning_steps": orch["reasoning_steps"],
    }
