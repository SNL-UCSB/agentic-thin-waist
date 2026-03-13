import json
from types import SimpleNamespace

from app.engine.intent_parser import IntentParser


class DummyClaudeClient:
    """Minimal stand-in for ClaudeClient for unit tests."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_message = None

    def send_with_default_system(self, user_message: str) -> str:
        # Record the last message for potential inspection in tests
        self.last_message = user_message
        return self.response_text


def test_intent_parser_extracts_plain_json():
    payload = {
        "applications": ["youtube"],
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "aqm_policy": "fq_codel",
        "duration_seconds": 60,
        "num_trials": 1,
        "clarification_needed": [],
        "design_type": ["isolated"],
        "reasoning": "Simple YouTube test at 10 Mbps.",
    }
    dummy = DummyClaudeClient(response_text=json.dumps(payload))
    parser = IntentParser(dummy)  # type: ignore[arg-type]

    result = parser.parse("Run a YouTube test at 10 Mbps")

    assert result["applications"] == ["youtube"]
    assert result["capacities"] == [10]
    assert result["design_type"] == ["isolated"]
    assert "YouTube" in result["reasoning"] or "youtube" in result["reasoning"]


def test_intent_parser_extracts_json_from_code_block():
    inner = {
        "applications": ["zoom"],
        "capacities": None,
        "latencies": [500],
        "cc_algorithms": None,
        "aqm_policy": None,
        "duration_seconds": None,
        "num_trials": 1,
        "clarification_needed": ["capacity range"],
        "design_type": ["needs_clarification"],
        "reasoning": "Very high latency for Zoom; capacity unspecified.",
    }
    wrapped = "Here is the JSON:\n```json\n" + json.dumps(inner) + "\n```"
    dummy = DummyClaudeClient(response_text=wrapped)
    parser = IntentParser(dummy)  # type: ignore[arg-type]

    result = parser.parse("What happens to Zoom at 500ms latency?")

    assert result["applications"] == ["zoom"]
    assert result["latencies"] == [500]
    assert result["design_type"] == ["needs_clarification"]
    assert "Zoom" in result["reasoning"] or "zoom" in result["reasoning"]
