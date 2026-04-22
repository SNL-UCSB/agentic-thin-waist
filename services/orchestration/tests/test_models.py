from pydantic import ValidationError

from app.models.schemas import (
    GeneratedExperiment,
    OrchestrationProgress,
    OrchestrationResponse,
    OrchestrationResult,
    OrchestrationStatus,
    ReasoningStep,
    ResearchIntent,
)


def test_research_intent_valid():
    intent = ResearchIntent(
        intent="Test YouTube at 10 Mbps",
        context={"user": "haarika"},
        preferences={"priority": "high"},
    )
    assert intent.intent == "Test YouTube at 10 Mbps"
    assert intent.context["user"] == "haarika"
    assert intent.preferences["priority"] == "high"


def test_research_intent_requires_intent_field():
    try:
        ResearchIntent()  # type: ignore[call-arg]
    except ValidationError as exc:
        assert "intent" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for missing intent")


def test_generated_experiment_defaults_and_types():
    exp = GeneratedExperiment(
        experiment_id="exp-1",
        capacity_mbps=10.0,
        latency_ms=50.0,
    )
    assert exp.application_type == "shell"
    assert exp.loss_rate == 0.0
    assert exp.duration_seconds == 60
    assert exp.num_trials == 1
    assert exp.cc_algorithm == "cubic"
    assert exp.aqm_policy == "pfifo"
    assert exp.ctp_cluster is None
    assert exp.ctp_capacity_range == {"lower_value": 1.0, "higher_value": 10.0}
    assert exp.reasoning == ""


def test_generated_experiment_rejects_invalid_types():
    try:
        GeneratedExperiment(  # type: ignore[misc]
            experiment_id="exp-1",
            capacity_mbps="not-a-float",  # type: ignore[arg-type]
            latency_ms=50.0,
        )
    except ValidationError as exc:
        assert "capacity_mbps" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid capacity_mbps")


def test_orchestration_response_valid():
    resp = OrchestrationResponse(
        orchestration_id="orch-1234",
        status=OrchestrationStatus.pending,
        intent="Test YouTube at 10 Mbps",
        generated_experiments=0,
    )
    assert resp.status == OrchestrationStatus.pending
    assert resp.generated_experiments == 0
    assert resp.claude_model == "claude-sonnet-4-6"
    assert resp.estimated_duration_minutes is None


def test_reasoning_step_valid():
    step = ReasoningStep(
        step=1,
        action="parse_intent",
        input={"intent": "Test YouTube at 10 Mbps"},
        output={"applications": ["youtube"]},
        reasoning="Identified youtube as the target application.",
    )
    assert step.step == 1
    assert step.action == "parse_intent"
    assert step.input["intent"].startswith("Test YouTube")


def test_orchestration_progress_valid():
    progress = OrchestrationProgress(
        orchestration_id="orch-1234",
        status=OrchestrationStatus.generating,
        progress={"stage": "generating", "percent": 50},
        generated_experiments=[{"experiment_id": "exp-1"}],
    )
    assert progress.status == OrchestrationStatus.generating
    assert progress.generated_experiments[0]["experiment_id"] == "exp-1"


def test_orchestration_result_valid():
    result = OrchestrationResult(
        orchestration_id="orch-1234",
        intent="Test YouTube at 10 Mbps",
        status=OrchestrationStatus.complete,
        experiment_results=[{"experiment_id": "exp-1", "throughput_mbps": 9.5}],
        summary={"conclusion": "YouTube performs well at 10 Mbps."},
    )
    assert result.status == OrchestrationStatus.complete
    assert result.summary["conclusion"].startswith("YouTube performs well")
