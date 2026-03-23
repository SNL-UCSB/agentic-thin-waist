#!/usr/bin/env python
"""Run Step 6 example intents through IntentParser and write output to example.md."""

import json
from pathlib import Path

from app.engine.claude_client import ClaudeClient
from app.engine.intent_parser import IntentParser

# Intents from INTEGRATION_PLAN.md Step 6 table (6-8 examples)
INTENTS = [
    "Run YouTube at 10 Mbps",
    "Test YouTube at 10, 25, 50 Mbps",
    "Compare YouTube vs Zoom at 25 Mbps",
    "Compare CUBIC vs BBR for YouTube at 10 Mbps",
    "How does Netflix perform?",
    "YouTube and Zoom at 10, 25, 50 Mbps",
    "YouTube at 10 Mbps with high-burstiness cross-traffic",
    "YouTube, 10 Mbps, 50ms, CUBIC, fq_codel, 60s, 3 trials",
]


def main() -> None:
    client = ClaudeClient()
    parser = IntentParser(client)
    out_lines: list[str] = []

    for i, intent in enumerate(INTENTS):
        result = parser.parse(intent)
        reasoning = result.get("reasoning", "")

        if i > 0:
            out_lines.append("")
        out_lines.append('INTENT: "{}"'.format(intent.replace('"', '\\"')))
        out_lines.append("EXTRACTED:")
        out_lines.append(json.dumps(result, indent=2))
        out_lines.append('REASONING: "{}"'.format(reasoning.replace('"', '\\"').replace("\n", " ")))

    out_path = Path(__file__).parent / "app" / "prompts" / "examples.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Wrote {len(INTENTS)} examples to {out_path}")


if __name__ == "__main__":
    main()
