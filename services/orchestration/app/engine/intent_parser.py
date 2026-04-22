"""Intent → structured parameters parser (Step 5).

This module uses Claude, conditioned on the Thin Waist system prompt and
knowledge files (via ClaudeClient.send_with_default_system), to extract
structured experiment parameters from a natural-language research intent.
"""

import json
from pathlib import Path
from typing import Any, Dict

from app.engine.claude_client import ClaudeClient


class IntentParser:
    """Use Claude to extract structured parameters from a natural-language intent."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self.claude = claude_client

    def parse(self, intent: str, use_examples: bool = False) -> Dict[str, Any]:
        """Parse a natural-language research intent into a structured dict.

        The returned dict is designed to be consumed by the ExperimentGenerator
        in Step 7. It should contain (when possible):

        - applications: list[str]
        - capacities: list[float] | None
        - latencies: list[float] | None
        - cc_algorithms: list[str] | None
        - aqm_policy: str | None
        - ctp_cluster: str | None
        - ctp_capacity_range: dict with keys lower_value/higher_value in Mbps
        - duration_seconds: int | None
        - num_trials: int
        - clarification_needed: list[str]
        - design_type: list[str] where each element is
          "isolated" | "concurrent" | "full" | "needs_clarification"
        - reasoning: str
        """
        examples_block = ""
        if use_examples:
            base_dir = Path(__file__).parent.parent
            examples_path = base_dir / "prompts" / "examples.md"
            if examples_path.exists():
                examples_text = examples_path.read_text()
                examples_block = (
                    "Here are a few prior intents and their extracted parameters "
                    "for you to use as reference examples only. Do not echo them "
                    "in your response; just use them to calibrate your behaviour.\n\n"
                    + examples_text
                    + "\n\nNow, independently of those examples, "
                    "extract parameters for the NEW intent below.\n\n"
                )

        extraction_prompt = f"""
{examples_block}Extract experiment parameters from the following research intent.

You already know the valid applications, parameter ranges, defaults,
and constraints from your Thin Waist system prompt and knowledge files.
Use that knowledge to interpret the intent, but DO NOT invent parameters
that the user has not implied. Prefer asking for clarification when needed.

Return ONLY a JSON object with these fields:
- applications: list of application names
- capacities: list of capacity values in Mbps (or null if not specified)
- latencies: list of latency values in ms (or null if not specified)
- cc_algorithms: list of CC algorithms (or null if not specified)
- aqm_policy: string (or null if not specified)
- ctp_cluster: string (cross-traffic profile cluster id from CTP knowledge, or null if not specified)
- ctp_capacity_range: object describing CTP selection range in Mbps with:
    - lower_value: minimum CTP capacity in Mbps
    - higher_value: maximum CTP capacity in Mbps
  If the user does not specify this, default to:
  {{"lower_value": 1, "higher_value": 10}}
- duration_seconds: integer (or null if not specified)
- num_trials: integer (default 1)
- clarification_needed: list of strings describing what needs clarification
- design_type: list of strings, one per implied experiment in the design,
      each of which is "isolated" | "concurrent" | "full" | "needs_clarification"
- reasoning: string explaining your interpretation

Intent: {intent}
"""
        response = self.claude.send_with_default_system(extraction_prompt)

        json_str = self._extract_json(response)
        result = json.loads(json_str)
        # Ensure optional fields exist so downstream never sees a missing key
        result.setdefault("ctp_cluster", None)
        result.setdefault("ctp_capacity_range", {"lower_value": 1, "higher_value": 10})
        return result

    def _extract_json(self, text: str) -> str:
        """Extract JSON from Claude's response, handling markdown code blocks.

        Claude may wrap the JSON in ```json ... ``` or ``` ... ``` fences.
        If no fences are present, the entire text is assumed to be JSON.
        """
        if "```json" in text:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            return text[start:end].strip()
        if "```" in text:
            start = text.index("```") + len("```")
            end = text.index("```", start)
            return text[start:end].strip()
        return text.strip()
