import json
import sys
from pathlib import Path

# Ensure the orchestration service root is on sys.path so that the `app` package
# can be imported when this script is run directly.
CURRENT_DIR = Path(__file__).resolve()
ORCH_ROOT = CURRENT_DIR.parents[1]
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from app.engine.claude_client import ClaudeClient  # type: ignore[import]
from app.engine.intent_parser import IntentParser  # type: ignore[import]

TEST_INPUTS = [
    {
        "id": "mixed_youtube_zoom_latency_sweep",
        "intent": "Compare YouTube and Zoom performance over a latency sweep at 20, 80, and 150 ms on a 25 Mbps link.",
    },
    {
        "id": "netflix_zoom_concurrent_low_capacity",
        "intent": "Study how Netflix and Zoom behave together on a congested 5 Mbps link with default latency.",
    },
    {
        "id": "twitch_vs_youtube_capacity_and_ctp",
        "intent": "Compare Twitch vs YouTube at 8, 20, and 40 Mbps under a light background browsing cross-traffic pattern.",
    },
    {
        "id": "zoom_reliability_high_latency_loss",
        "intent": "Evaluate Zoom call reliability at 10 Mbps under 100, 200, and 400 ms latency with 1% loss.",
    },
    {
        "id": "discord_google_meet_multi_app",
        "intent": "Run Discord and Google Meet together at 15 Mbps to understand how they share bandwidth.",
    },
]


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    output_dir = base_dir / "app" / "experiment_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    claude = ClaudeClient()
    parser = IntentParser(claude)

    for case in TEST_INPUTS:
        intent_id = case["id"]
        intent_text = case["intent"]

        # Baseline: without few-shot examples
        parsed_without = parser.parse(intent_text)

        # With few-shot examples from prompts/examples.md
        parsed_with = parser.parse(intent_text, use_examples=True)

        output_payload = {
            "intent_id": intent_id,
            "intent": intent_text,
            "without_examples": parsed_without,
            "with_examples": parsed_with,
        }

        out_path = output_dir / f"{intent_id}.json"
        out_path.write_text(json.dumps(output_payload, indent=2))


if __name__ == "__main__":
    main()
