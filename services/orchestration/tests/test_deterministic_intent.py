from app.agent.orchestrator import agent as orch_agent
from app.engine.deterministic_intent import (
    build_parsed_intent,
    build_workflow_parameters,
)
from app.engine.experiment_generator import ExperimentGenerator


def test_build_workflow_parameters_uses_nested_and_top_level_fields():
    ctx = {
        "meeting_id": "111222333",
        "passcode": "pc",
        "display_name": "Receiver2",
        "wait_seconds": 60,
        "workflow_parameters": {"display_name": "OverrideName"},
        "extra": "ignored",
    }
    params = build_workflow_parameters(ctx, "run_zoom_receive_workflow")
    assert params == {
        "meeting_id": "111222333",
        "passcode": "pc",
        "display_name": "OverrideName",
        "wait_seconds": 60,
    }


def test_build_parsed_intent_for_zoom_context():
    ctx = {
        "application": "zoom",
        "applications": ["zoom"],
        "application_type": "shell",
        "capacities": [10],
        "latencies": [10],
        "cc_algorithms": ["cubic"],
        "aqm_policy": "pfifo",
        "duration_seconds": 60,
        "num_trials": 1,
        "workflow_parameters": {
            "meeting_id": "111222333",
            "passcode": "pc",
            "display_name": "Receiver2",
            "wait_seconds": 60,
        },
    }
    parsed = build_parsed_intent(ctx, intent="zoom receive", workflow_id="run_zoom_receive_workflow")
    assert parsed["applications"] == ["zoom"]
    assert parsed["application_type"] == "shell"
    assert parsed["capacities"] == [10]
    assert parsed["latencies"] == [10]
    assert parsed["cc_algorithms"] == ["cubic"]
    assert parsed["aqm_policy"] == "pfifo"
    assert parsed["workflow_parameters"]["meeting_id"] == "111222333"


def test_parse_intent_bypass_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(orch_agent, "save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        orch_agent,
        "get_model",
        lambda: (_ for _ in ()).throw(AssertionError("get_model should not be called")),
    )
    state = {
        "orchestration_id": "orch-test",
        "intent": "Join Zoom receive-only",
        "bypass_llm": True,
        "workflow_id": "run_zoom_receive_workflow",
        "context": {
            "applications": ["zoom"],
            "application_type": "shell",
            "capacities": [10],
            "latencies": [10],
            "cc_algorithms": ["cubic"],
            "aqm_policy": "pfifo",
            "workflow_parameters": {
                "meeting_id": "111222333",
                "passcode": "pc",
                "display_name": "Receiver2",
                "wait_seconds": 60,
            },
        },
    }
    out = orch_agent.parse_intent(state)
    parsed = out["parsed_intent"]
    assert parsed["applications"] == ["zoom"]
    assert parsed["workflow_parameters"]["display_name"] == "Receiver2"


def test_experiment_id_prefix_matches_zoom_shaping_signature():
    parsed = build_parsed_intent(
        {
            "applications": ["zoom"],
            "application_type": "shell",
            "capacities": [10],
            "latencies": [10],
            "cc_algorithms": ["cubic"],
            "aqm_policy": "pfifo",
            "ctp_name": "cluster0tree1profile1234",
        },
        workflow_id="run_zoom_receive_workflow",
    )
    exp = ExperimentGenerator().generate(parsed)[0]
    assert exp.experiment_id.startswith("zoom_10_10_10_pfifo_cubic_cluster0tree1profile1234_")
