#!/usr/bin/env python3
"""Lightweight CLI for the Agentic Thin Waist orchestration service.

Wraps the four most common interactions with the orchestrator so users do
not have to hand-roll curl invocations (issue #145).

Subcommands:

    intent "<natural-language description>"     Submit a research intent.
                                                Prints the orchestration_id.
    status <orchestration_id>                   Poll status every 5s and print
                                                a one-line summary per tick.
                                                Stops at a terminal state
                                                (complete, failed).
    get_id <orchestration_id>                   Print the generated experiment
                                                IDs (one per line) for an
                                                orchestration.
    debug <orchestration_id>                    Print a detailed dump:
                                                status, lifecycle stages,
                                                detailed progress flags,
                                                reasoning steps, and any
                                                error.

The orchestrator's base URL defaults to ``http://localhost:8005`` and can
be overridden with ``--url`` or the ``ORCH_URL`` environment variable.

Pure stdlib — no third-party deps so the CLI can be installed by copying
this single file or invoked directly with ``python orch_cli.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "http://localhost:8005"
TERMINAL_STATUSES = {"complete", "failed", "canceled", "cancelled"}
POLL_INTERVAL_SECONDS = 5.0


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    """Issue one HTTP request and return (status_code, parsed_body).

    Body is parsed as JSON when possible; otherwise the raw text is returned.
    HTTP errors (4xx/5xx) are returned with their parsed body rather than
    raised, so callers can render structured error responses from the API.
    """
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw.decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(
            f"error: cannot reach orchestrator at {url}: {exc.reason}", file=sys.stderr
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_intent(args: argparse.Namespace) -> int:
    """Submit a natural-language intent. Prints the orchestration_id on success."""
    payload = {"intent": args.text, "context": {}, "preferences": {}}
    status, body = _request(args.url, "POST", "/intent", payload=payload)
    if status >= 400 or not isinstance(body, dict) or "orchestration_id" not in body:
        print(f"error: /intent returned HTTP {status}: {body}", file=sys.stderr)
        return 1
    print(body["orchestration_id"])
    return 0


def _status_summary(d: dict) -> str:
    """One-line summary of an orchestration status payload."""
    status = d.get("status", "?")
    exps = d.get("generated_experiments", []) or []
    progress = (d.get("detailed_progress") or {}).get(
        "iteration_phase_completion"
    ) or {}
    done = (progress.get("complete") or {}).get("completed_iterations", 0)
    failed = (progress.get("failed") or {}).get("completed_iterations", 0)
    total = (progress.get("complete") or {}).get("total_iterations", len(exps))
    err = d.get("error")
    line = (
        f"status={status}  experiments={len(exps)}  "
        f"complete={done}/{total}  failed={failed}"
    )
    if err:
        line += f"  error={err}"
    return line


def cmd_status(args: argparse.Namespace) -> int:
    """Poll orchestration status every 5s until terminal, printing a summary each tick."""
    last_line = None
    while True:
        status_code, body = _request(args.url, "GET", f"/orchestration/{args.orch_id}")
        if status_code == 404:
            print(f"error: orchestration {args.orch_id} not found", file=sys.stderr)
            return 1
        if status_code >= 400 or not isinstance(body, dict):
            print(
                f"error: /orchestration returned HTTP {status_code}: {body}",
                file=sys.stderr,
            )
            return 1
        line = _status_summary(body)
        # Only reprint when the summary changes — keeps the polling output
        # readable when the orchestration sits in a single state for a while.
        if line != last_line:
            print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)
            last_line = line
        if body.get("status") in TERMINAL_STATUSES:
            return 0 if body.get("status") == "complete" else 1
        time.sleep(POLL_INTERVAL_SECONDS)


def cmd_get_id(args: argparse.Namespace) -> int:
    """Print the generated experiment IDs (one per line) for an orchestration."""
    status, body = _request(args.url, "GET", f"/orchestration/{args.orch_id}")
    if status == 404:
        print(f"error: orchestration {args.orch_id} not found", file=sys.stderr)
        return 1
    if status >= 400 or not isinstance(body, dict):
        print(f"error: /orchestration returned HTTP {status}: {body}", file=sys.stderr)
        return 1
    exps = body.get("generated_experiments") or []
    if not exps:
        print(
            f"note: no experiments generated yet (status={body.get('status')})",
            file=sys.stderr,
        )
        return 0
    for exp in exps:
        exp_id = (exp or {}).get("experiment_id")
        if exp_id:
            print(exp_id)
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    """Print a detailed multi-section dump of an orchestration."""
    status, body = _request(args.url, "GET", f"/orchestration/{args.orch_id}")
    if status == 404:
        print(f"error: orchestration {args.orch_id} not found", file=sys.stderr)
        return 1
    if status >= 400 or not isinstance(body, dict):
        print(f"error: /orchestration returned HTTP {status}: {body}", file=sys.stderr)
        return 1

    # Pull complementary endpoints. Reasoning is optional — if it fails (e.g.
    # the orchestration is too old, or the agent didn't produce reasoning),
    # the debug output should still render the rest.
    _, results_body = _request(
        args.url, "GET", f"/orchestration/{args.orch_id}/results"
    )
    reasoning_status, reasoning_body = _request(
        args.url, "GET", f"/orchestration/{args.orch_id}/reasoning"
    )

    print(f"=== orchestration {args.orch_id} ===")
    print(f"status      : {body.get('status')}")
    if body.get("error"):
        print(f"error       : {body.get('error')}")

    exps = body.get("generated_experiments") or []
    print(f"experiments : {len(exps)} generated")
    for exp in exps:
        spec = exp or {}
        print(
            f"  - {spec.get('experiment_id'):<48} cc={spec.get('cc_algorithm')} "
            f"cap={spec.get('capacity_mbps')}Mbps lat={spec.get('latency_ms')}ms "
            f"qdisc={spec.get('aqm_policy')} trials={spec.get('num_trials')}"
        )

    stages = body.get("lifecycle_stages") or []
    if stages:
        print(f"\nlifecycle ({len(stages)} stages):")
        for s in stages:
            print(
                f"  - stage={s.get('stage')} timestamp={s.get('timestamp')} "
                f"experiment_id={s.get('experiment_id')}"
            )

    dp = body.get("detailed_progress") or {}
    if dp:
        print("\ndetailed_progress:")
        print(json.dumps(dp, indent=2))

    if isinstance(results_body, dict):
        results = results_body.get("results") or []
        if results:
            print(f"\nresults ({len(results)} executed):")
            for r in results:
                run = r.get("run") or {}
                cc = (run.get("congestion") or {}).get("current_algorithm")
                observed = (run.get("workflow_result") or {}).get(
                    "congestion_observed", {}
                )
                print(
                    f"  - {r.get('experiment_id'):<48} status={r.get('status')} "
                    f"cc_set={cc} observed={observed}"
                )

    if reasoning_status < 400 and isinstance(reasoning_body, dict):
        steps = reasoning_body.get("reasoning_steps") or []
        if steps:
            print(f"\nreasoning ({len(steps)} steps):")
            for i, step in enumerate(steps, start=1):
                if isinstance(step, dict):
                    summary = step.get("summary") or step.get("content") or step
                else:
                    summary = step
                print(f"  [{i}] {summary}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orch",
        description=(
            "CLI for the Agentic Thin Waist orchestration service. "
            "See `orch <subcommand> --help` for details."
        ),
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("ORCH_URL", DEFAULT_URL),
        help=(
            "Base URL of the orchestration service "
            f"(default: $ORCH_URL or {DEFAULT_URL})"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="subcommand")

    p_intent = sub.add_parser("intent", help="Submit a natural-language intent")
    p_intent.add_argument("text", help="The natural-language intent")
    p_intent.set_defaults(func=cmd_intent)

    p_status = sub.add_parser(
        "status",
        help="Poll status every 5s until terminal (complete/failed)",
    )
    p_status.add_argument("orch_id", help="Orchestration ID returned by `intent`")
    p_status.set_defaults(func=cmd_status)

    p_get_id = sub.add_parser(
        "get_id", help="Print generated experiment IDs (one per line)"
    )
    p_get_id.add_argument("orch_id", help="Orchestration ID")
    p_get_id.set_defaults(func=cmd_get_id)

    p_debug = sub.add_parser(
        "debug",
        help="Print detailed status, lifecycle, results, and reasoning",
    )
    p_debug.add_argument("orch_id", help="Orchestration ID")
    p_debug.set_defaults(func=cmd_debug)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
