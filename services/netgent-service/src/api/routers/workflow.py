"""Workflow routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter, status

from ..schemas import (
    AvailableWorkflowItem,
    AvailableWorkflowsResponse,
    CompileWorkflowRequest,
    CompileWorkflowResponse,
    ExecuteWorkflowRequest,
    ExecuteWorkflowResponse,
    NfaSummary,
    ValidateWorkflowRequest,
    ValidateWorkflowResponse,
    WorkflowArtifacts,
    WorkflowMetrics,
    WorkflowResultResponse,
    WorkflowState,
    WorkflowTransition,
)


router = APIRouter()


@router.post(
    "/execute",
    response_model=ExecuteWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def execute_workflow(
    request: ExecuteWorkflowRequest,
) -> ExecuteWorkflowResponse:
    return ExecuteWorkflowResponse(workflow_id="wf-executed-abc123", status="completed", start_time="2026-03-04T10:00:00Z", estimated_completion="2026-03-04T10:02:05Z")


@router.post(
    "/compile",
    response_model=CompileWorkflowResponse,
)
def compile_workflow(
    request: CompileWorkflowRequest,
) -> CompileWorkflowResponse:
    return CompileWorkflowResponse(
        workflow_id="wf-compiled-abc123",
        states=[
            WorkflowState(
                id="init",
                action="initialize_browser",
            ),
            WorkflowState(
                id="navigate",
                action="goto",
                parameters={"url": "https://netflix.com"},
            ),
            WorkflowState(
                id="login",
                action="enter_credentials",
                parameters={"selectors": ["email", "password"]},
            ),
            WorkflowState(
                id="select",
                action="click_video",
            ),
            WorkflowState(
                id="play",
                action="wait",
                parameters={"duration": 30},
            ),
        ],
        transitions=[
            WorkflowTransition(from_state="init", to_state="navigate"),
            WorkflowTransition(from_state="navigate", to_state="login"),
            WorkflowTransition(from_state="login", to_state="select"),
            WorkflowTransition(from_state="select", to_state="play"),
        ],
        estimated_duration_seconds=35,
        validation_status="passed",
    )


@router.post(
    "/validate",
    response_model=ValidateWorkflowResponse,
)
def validate_workflow(
    request: ValidateWorkflowRequest,
) -> ValidateWorkflowResponse:
    return ValidateWorkflowResponse(valid=True, errors=[], warnings=[], estimated_duration_seconds=62, state_count=3)


@router.get(
    "/available",
    response_model=AvailableWorkflowsResponse,
)
def get_available_workflows(
) -> AvailableWorkflowsResponse:
    return AvailableWorkflowsResponse(
        applications=[
            AvailableWorkflowItem(
                application="youtube",
                execution_type="browser",
                supported_qoe_metrics=[
                    "startup_time_ms",
                    "rebuffer_events",
                    "bitrate",
                ],
                prerequisites=["youtube_url"],
                notes="Requires YouTube URL",
            )
        ]
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResultResponse,
)
def get_workflow(
    workflow_id: str,
) -> WorkflowResultResponse:
    return WorkflowResultResponse(
        workflow_id=workflow_id,
        status="completed",
        states_executed=["init", "navigate", "search", "play", "watch", "close"],
        duration=65.2,
        nfa=NfaSummary(
            states=6,
            transitions=5,
            initial_state="init",
            accepting_states=["close"],
        ),
        artifacts=WorkflowArtifacts(
            har_file="s3://artifacts/wf-uuid-001.har",
            console_log="s3://artifacts/wf-uuid-001.log",
            screenshots=["s3://artifacts/wf-uuid-001-state1.png"],
        ),
        qoe_metrics=WorkflowMetrics(
            video_startup_time_ms=2500,
            mean_bitrate_mbps=8.5,
            rebuffer_events=1,
            rebuffer_duration_ms=2000,
            bitrate_changes=3,
            max_bitrate_mbps=9.5,
            min_bitrate_mbps=4.2,
            latency_ms=100,
            packet_loss_percent=0.1,
            throughput_mbps=10,
        ),
        errors=[],
    )
