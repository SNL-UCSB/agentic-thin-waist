"""End-to-end test: API → IntentParser → ExperimentGenerator → config + orchestration_id.

WARNING: This test uses the REAL API and real Claude (IntentParser). It requires
ANTHROPIC_API_KEY to be set and will make live API calls. Run with:
  pytest services/orchestration/tests/test_end_to_end_real_api_warning.py -v -s

The -s flag is required to see printed output (parser result, experiment config, id).
"""

import os
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.engine.claude_client import ClaudeClient
from app.engine.intent_parser import IntentParser
from app.engine.experiment_generator import ExperimentGenerator

# Intent used for the full flow
INTENT = "Discord and Youtube at 50 Mbps and 100ms"

# Require API key for this module (real API warning)
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; this test uses real Claude API",
)


def test_end_to_end():
    """
    Run full flow: parse intent → generate experiments → call API → print config and id.
    Prints: (1) intent parser result, (2) experiment generator config, (3) orchestration_id.
    """
    print("\n" + "=" * 60)
    print("END-TO-END: Intent → Parser → Generator → API (orchestration_id)")
    print("=" * 60)
    print(f"Intent: {INTENT!r}\n")

    # --- 1. Intent Parser (real Claude) ---
    print("--- 1. Intent Parser result ---")
    claude = ClaudeClient()
    parser = IntentParser(claude)
    parsed = parser.parse(INTENT)
    print(json.dumps(parsed, indent=2))
    print()

    # --- 2. Experiment Generator (config) ---
    print("--- 2. Experiment Generator config ---")
    generator = ExperimentGenerator()
    experiments = generator.generate(parsed)
    configs = [e.model_dump() for e in experiments]
    print(json.dumps(configs, indent=2))
    print()

    # --- 3. API: POST /intent and wait for completion ---
    print("--- 3. API: POST /intent and orchestration_id ---")
    client = TestClient(app)
    resp = client.post("/intent", json={"intent": INTENT})
    assert resp.status_code == 202, resp.text
    data = resp.json()
    orch_id = data["orchestration_id"]
    assert orch_id.startswith("orch-"), orch_id

    # Poll until complete
    for _ in range(60):
        status_resp = client.get(f"/orchestration/{orch_id}")
        assert status_resp.status_code == 200
        if status_resp.json()["status"] == "complete":
            break
        if status_resp.json()["status"] == "failed":
            pytest.fail(f"Orchestration failed: {status_resp.json()}")
        time.sleep(0.5)
    else:
        pytest.fail("Orchestration did not complete within 30 seconds")

    # Print orchestration_id for the user
    print(f"Orchestration ID: {orch_id}")
    print("=" * 60 + "\n")

    # Assert we got experiments from the API as well
    final = status_resp.json()
    assert "generated_experiments" in final
    assert len(final["generated_experiments"]) >= 1
