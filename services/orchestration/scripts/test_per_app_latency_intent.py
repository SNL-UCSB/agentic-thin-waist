#!/usr/bin/env python3
"""End-to-end smoke test for concurrent per-application latency.

Requires the orchestration stack and privileged substrate workers to be running.

Usage from the repository root:

    python3 services/orchestration/scripts/test_per_app_latency_intent.py

Environment overrides:

    ORCH_URL=http://localhost:8005
    POLL_INTERVAL_SECONDS=3
    TIMEOUT_SECONDS=1200
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

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8005").rstrip("/")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "3"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "1200"))
TERMINAL_STATUSES = {"complete", "failed", "partial", "canceled", "cancelled"}

INTENT = (
    "Run three concurrent YouTube flows playing "
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ on a shared 6 Mbps bottleneck. "
    "Use 50 ms latency for youtube-1, 100 ms for youtube-2, and 0 ms for youtube-3 "
    "for 60 seconds using CUBIC congestion control and a pfifo queue."
)
EXPECTED_LATENCIES = {"youtube-1": 50.0, "youtube-2": 100.0, "youtube-3": 0.0}


def request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        ORCH_URL + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach {ORCH_URL}: {exc.reason}") from exc


def fail(message: str, details: Any = None) -> None:
    print(f"\nFAIL: {message}", file=sys.stderr)
    if details is not None:
        print(json.dumps(details, indent=2, default=str), file=sys.stderr)
    raise SystemExit(1)


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("execution_mode") != "concurrent":
        fail("experiment was not generated in concurrent mode", spec)
    if float(spec.get("capacity_mbps", -1)) != 6.0:
        fail("shared capacity is not 6 Mbps", spec)
    if spec.get("aqm_policy") != "pfifo":
        fail("queue discipline is not pfifo", spec)
    if str(spec.get("cc_algorithm", "")).lower() != "cubic":
        fail("congestion control is not cubic", spec)
    if int(spec.get("duration_seconds", -1)) != 60:
        fail("duration is not 60 seconds", spec)

    apps = [str(app).lower() for app in spec.get("applications") or []]
    if apps != ["youtube-1", "youtube-2", "youtube-3"]:
        fail("applications are missing or out of alignment", spec)
    if spec.get("application_types") != ["browser", "browser", "browser"]:
        fail("not every application was classified as browser", spec)

    actual = {
        str(config.get("instance_id") or config.get("application", "")).lower(): float(
            config["latency_ms"]
        )
        for config in spec.get("application_configs") or []
    }
    if actual != EXPECTED_LATENCIES:
        fail(
            "per-app latency mapping is incorrect",
            {"expected": EXPECTED_LATENCIES, "actual": actual},
        )
    if float(spec.get("latency_ms", -1)) != 0.0:
        fail("global latency must be zero when per-app lanes are used", spec)


def main() -> None:
    global ORCH_URL, POLL_INTERVAL, TIMEOUT_SECONDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=ORCH_URL, help="Orchestration service URL")
    parser.add_argument(
        "--poll", type=float, default=POLL_INTERVAL, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=TIMEOUT_SECONDS,
        help="Overall timeout in seconds",
    )
    args = parser.parse_args()
    ORCH_URL = args.url.rstrip("/")
    POLL_INTERVAL = args.poll
    TIMEOUT_SECONDS = args.timeout

    print(f"Orchestrator: {ORCH_URL}")
    print(f"Intent: {INTENT}\n")
    submitted = request(
        "POST",
        "/intent",
        {
            "intent": INTENT,
            "context": {},
            "preferences": {"max_parallel_workers": 1},
        },
    )
    orchestration_id = submitted.get("orchestration_id")
    if not orchestration_id:
        fail("submission did not return orchestration_id", submitted)
    print(f"Submitted: {orchestration_id}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    validated_spec = False
    previous_status = None
    status_body: dict[str, Any] = {}

    while time.monotonic() < deadline:
        status_body = request("GET", f"/orchestration/{orchestration_id}")
        status = str(status_body.get("status", "unknown"))
        experiments = status_body.get("generated_experiments") or []
        if status != previous_status:
            print(f"status={status} generated_experiments={len(experiments)}")
            previous_status = status

        if experiments and not validated_spec:
            concurrent = [
                spec
                for spec in experiments
                if spec.get("execution_mode") == "concurrent"
            ]
            if len(concurrent) != 1:
                fail("expected exactly one concurrent experiment", experiments)
            validate_spec(concurrent[0])
            validated_spec = True
            print("PASS: generated concurrent experiment spec is correct")

        if status in TERMINAL_STATUSES:
            break
        time.sleep(POLL_INTERVAL)
    else:
        fail(f"timed out after {TIMEOUT_SECONDS:.0f} seconds", status_body)

    results = request("GET", f"/orchestration/{orchestration_id}/results")
    if status_body.get("status") != "complete":
        reasoning = request("GET", f"/orchestration/{orchestration_id}/reasoning")
        fail(
            f"orchestration ended with status={status_body.get('status')}",
            {"status": status_body, "results": results, "reasoning": reasoning},
        )
    if not validated_spec:
        fail("orchestration completed without exposing a generated spec", status_body)

    executed = results.get("results") or []
    if len(executed) != 1 or executed[0].get("status") != "success":
        fail("concurrent experiment did not execute successfully", results)
    per_app_run = executed[0].get("run") or {}
    missing = set(EXPECTED_LATENCIES) - set(per_app_run)
    if missing:
        fail(f"missing per-app run results: {sorted(missing)}", results)

    print("PASS: concurrent per-app latency experiment completed successfully")
    print(json.dumps(executed[0], indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        fail(str(exc))
