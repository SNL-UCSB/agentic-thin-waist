#!/usr/bin/env python3
"""
Submit YouTube orchestration requests (25/50/75 Mbps), stream lifecycle updates
in real time, and print full final results.

Example:
  source ~/imp_files/virtualenvs/thinwaist/bin/activate
  cd services/orchestration
  python scripts/run_youtube_capacity_lifecycle_demo.py

Optional:
  python scripts/run_youtube_capacity_lifecycle_demo.py --base-url http://localhost:8003
  python scripts/run_youtube_capacity_lifecycle_demo.py --poll-seconds 1.0
  python scripts/run_youtube_capacity_lifecycle_demo.py --timeout-seconds 900
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from typing import Any

import httpx

DEFAULT_CAPACITIES = (25, 50, 75)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _title(msg: str) -> None:
    print(f"\n{'=' * 80}\n[{_now()}] {msg}\n{'=' * 80}")


def _line(msg: str) -> None:
    print(f"[{_now()}] {msg}")


def _dump(label: str, obj: Any) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(obj, indent=2, default=str))


def _submit_request(
    client: httpx.Client,
    *,
    base_url: str,
    capacity_mbps: int,
    duration_seconds: int,
) -> str:
    intent_text = (
        f"Run a single YouTube experiment at {capacity_mbps} Mbps capacity and "
        f"{duration_seconds} seconds duration. Execute immediately and collect results."
    )
    payload = {
        "intent": intent_text,
        "context": {
            "application": "youtube",
            "capacity_mbps": capacity_mbps,
            "duration_seconds": duration_seconds,
            "num_trials": 1,
        },
        "preferences": {
            "run_immediately": True,
            "use_examples": True,
        },
    }
    _title(f"Submitting request: YouTube @ {capacity_mbps} Mbps")
    _dump("POST /intent payload", payload)

    response = client.post(f"{base_url}/intent", json=payload, timeout=30.0)
    response.raise_for_status()
    body = response.json()
    _dump("POST /intent response", body)

    orch_id = body.get("orchestration_id")
    if not orch_id:
        raise RuntimeError(f"Missing orchestration_id in response: {body}")
    return str(orch_id)


def _print_new_lifecycle_stages(
    lifecycle_stages: list[dict[str, Any]],
    seen_count: int,
) -> int:
    if len(lifecycle_stages) <= seen_count:
        return seen_count
    for stage in lifecycle_stages[seen_count:]:
        name = stage.get("stage", "unknown_stage")
        detail = stage.get("detail")
        if detail:
            _line(f"lifecycle stage -> {name}: {detail}")
        else:
            _line(f"lifecycle stage -> {name}")
    return len(lifecycle_stages)


def _watch_orchestration(
    client: httpx.Client,
    *,
    base_url: str,
    orchestration_id: str,
    poll_seconds: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    status_url = f"{base_url}/orchestration/{orchestration_id}"
    deadline = time.monotonic() + timeout_seconds
    last_status: str | None = None
    seen_stage_count = 0

    _title(f"Streaming status for orchestration {orchestration_id}")
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Timed out waiting for orchestration {orchestration_id} after "
                f"{timeout_seconds} seconds"
            )
        response = client.get(status_url, timeout=30.0)
        response.raise_for_status()
        body = response.json()

        status = str(body.get("status", "unknown"))
        if status != last_status:
            _line(f"status -> {status}")
            last_status = status

        lifecycle_stages = body.get("lifecycle_stages") or []
        if isinstance(lifecycle_stages, list):
            seen_stage_count = _print_new_lifecycle_stages(
                lifecycle_stages,
                seen_stage_count,
            )

        if status in {"complete", "failed"}:
            _dump("Final /orchestration status payload", body)
            return body

        time.sleep(poll_seconds)


def _fetch_results(
    client: httpx.Client,
    *,
    base_url: str,
    orchestration_id: str,
) -> dict[str, Any]:
    response = client.get(
        f"{base_url}/orchestration/{orchestration_id}/results",
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    _dump("GET /orchestration/{id}/results payload", body)
    return body


def run_demo(
    *,
    base_url: str,
    capacities: tuple[int, ...],
    duration_seconds: int,
    poll_seconds: float,
    timeout_seconds: int,
) -> int:
    summary: list[dict[str, Any]] = []
    failures = 0

    _title("Starting YouTube capacity lifecycle demo")
    _line(f"Base URL: {base_url}")
    _line(f"Capacities: {capacities}")
    _line(f"Duration seconds per run: {duration_seconds}")
    _line(f"Poll interval: {poll_seconds}s")
    _line(f"Timeout per orchestration: {timeout_seconds}s")

    with httpx.Client() as client:
        for capacity in capacities:
            try:
                orch_id = _submit_request(
                    client,
                    base_url=base_url,
                    capacity_mbps=capacity,
                    duration_seconds=duration_seconds,
                )
                status_payload = _watch_orchestration(
                    client,
                    base_url=base_url,
                    orchestration_id=orch_id,
                    poll_seconds=poll_seconds,
                    timeout_seconds=timeout_seconds,
                )
                results_payload = _fetch_results(
                    client,
                    base_url=base_url,
                    orchestration_id=orch_id,
                )
                summary.append(
                    {
                        "capacity_mbps": capacity,
                        "orchestration_id": orch_id,
                        "status": status_payload.get("status"),
                        "results_count": len(results_payload.get("results", [])),
                    }
                )
            except Exception as exc:
                failures += 1
                _title(f"Run failed for {capacity} Mbps")
                _line(f"{type(exc).__name__}: {exc}")
                summary.append(
                    {
                        "capacity_mbps": capacity,
                        "orchestration_id": None,
                        "status": "failed_to_run",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    _title("Demo summary")
    print(json.dumps(summary, indent=2, default=str))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Orchestration API base URL.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=20,
        help="Requested experiment duration in seconds.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.5,
        help="Polling interval for status updates.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Max wait time per orchestration before timing out.",
    )
    args = parser.parse_args()

    return run_demo(
        base_url=args.base_url.rstrip("/"),
        capacities=DEFAULT_CAPACITIES,
        duration_seconds=args.duration_seconds,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
