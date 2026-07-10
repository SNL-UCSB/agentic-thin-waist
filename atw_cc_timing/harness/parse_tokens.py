#!/usr/bin/env python3
"""Measure the orchestrator's intent->config (parse_intent) token cost for a
given intent string, EXACTLY as the running orchestration service builds it.

The service (services/orchestration/app/agent/orchestrator/prompts.py) builds the
parse_intent prompt as:
    SYSTEM = system.md + sorted(knowledge/*.md, each with a "# <stem>" header)
    HUMAN  = examples_block(examples.md) + <fixed instruction> + "Intent: " + intent
The provider is Gemini (ORCHESTRATOR_LLM_PROVIDER=gemini, model gemini-3.1-flash-lite).

We reconstruct that exact text and query Gemini's countTokens for the INPUT, and
count the parse OUTPUT (the ParsedIntent JSON, fetched from the orchestration
reasoning endpoint) the same way. This yields the precise per-intent token cost of
the intent->networking-config conversion.

Usage:
    parse_tokens.py input  "<intent>"                 -> prints input_tokens
    parse_tokens.py output '<parsed_json_string>'     -> prints output_tokens
    parse_tokens.py both   "<intent>" '<parsed_json>' -> prints "in out"
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path("/home/jaber/agentic-thin-waist")
ORCH = REPO / "services/orchestration/app"
MODEL = "gemini-3.1-flash-lite"


def _api_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GOOGLE_API_KEY not found in .env")


def build_system() -> str:
    text = (ORCH / "prompts/system.md").read_text()
    for kf in sorted((ORCH / "knowledge").glob("*.md")):
        text += f"\n\n# {kf.stem}\n\n" + kf.read_text()
    return text


def build_examples_block() -> str:
    ex = ORCH / "prompts/examples.md"
    if not ex.exists():
        return ""
    return (
        "Here are a few prior intents and their extracted parameters "
        "for you to use as reference examples only. Do not echo them "
        "in your response; just use them to calibrate your behaviour.\n\n"
        + ex.read_text()
        + "\n\nNow, independently of those examples, "
        "extract parameters for the NEW intent below.\n\n"
    )


INSTRUCTION = """Extract experiment parameters from the following research intent.

You already know the valid applications, parameter ranges, defaults,
and constraints from your Thin Waist system prompt and knowledge files.
Use that knowledge to interpret the intent, but DO NOT invent parameters
that the user has not implied. Prefer asking for clarification when needed.

Return ONLY a JSON object containing:
- applications
- application_type
- capacities
- latencies
- cc_algorithms
- aqm_policy
- buffer_packets
- qdisc_params
- ctp_cluster
- ctp_capacity_range
- duration_seconds
- workflow_parameters
- num_trials
- clarification_needed
- design_type
- reasoning

Intent: """


def full_input_prompt(intent: str) -> str:
    return build_system() + "\n\n" + build_examples_block() + INSTRUCTION + intent


def count_tokens(text: str) -> int:
    key = _api_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:countTokens?key={key}"
    )
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": text}]}]}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["totalTokens"]


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "input":
        print(count_tokens(full_input_prompt(sys.argv[2])))
    elif mode == "output":
        print(count_tokens(sys.argv[2]))
    elif mode == "both":
        print(count_tokens(full_input_prompt(sys.argv[2])), count_tokens(sys.argv[3]))
    else:
        raise SystemExit("mode must be input|output|both")
