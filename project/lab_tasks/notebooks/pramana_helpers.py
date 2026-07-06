"""
Helper functions for the Pramana demo notebook.

Everything the notebook needs — service URLs, HTTP calls, the polling loop,
telemetry queries, and result formatting is in here so the notebook stays simple.

Public API (imported via ``from pramana_helpers import *``):
    run_and_display(intent)   submit an intent, wait for it, print a plain-English summary
    show_history()            print a clean table of recent experiments from telemetry
"""

from __future__ import annotations

import math
import time
from typing import Any

import requests

try:  # tables inside Jupyter; degrade gracefully outside it
    import pandas as pd
except Exception:  # pragma: no cover - pandas is expected but optional
    pd = None

try:
    from IPython.display import display
except Exception:  # pragma: no cover - not running under IPython

    def display(obj: Any) -> None:
        print(obj)


__all__ = ["run_and_display", "show_history", "ORCH", "TELEMETRY"]

# ── Service endpoints (local stack) ──────────────────────────────────────────
ORCH = "http://localhost:8005"  # orchestration service
TELEMETRY = "http://localhost:8004"  # telemetry service
TIMEOUT = 30  # per-request timeout (seconds)

_TERMINAL = {"complete", "completed", "failed"}
_POLL_EVERY = 5  # seconds between status polls
_MAX_POLLS = 360  # generous cap (~30 min) for sweeps / multi-app / browser runs


# ── Formatting helpers ───────────────────────────────────────────────────────
def _is_missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _num(v: Any) -> str:
    """Render a number without a trailing .0 for whole values."""
    if _is_missing(v):
        return "n/a"
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _measure(v: Any, unit: str, nd: int = 2) -> str:
    if _is_missing(v):
        return "n/a"
    return f"{round(float(v), nd):g} {unit}"


def _app_name(experiment_id: str | None, fallback: str = "unknown") -> str:
    """Experiment ids are ``<app>_<cap>_<...>`` — the first token is the app."""
    if not experiment_id:
        return fallback
    return experiment_id.split("_", 1)[0]


# ── HTTP building blocks ─────────────────────────────────────────────────────
def _submit_intent(intent: str) -> str:
    resp = requests.post(f"{ORCH}/intent", json={"intent": intent}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["orchestration_id"]


def _poll(orch_id: str) -> dict[str, Any]:
    last = None
    body: dict[str, Any] = {}
    started = time.time()
    for _ in range(_MAX_POLLS):
        body = requests.get(f"{ORCH}/orchestration/{orch_id}", timeout=TIMEOUT).json()
        status = body.get("status")
        if status != last:
            print(f"  {status} ... ({int(time.time() - started)}s)")
            last = status
        if status in _TERMINAL:
            break
        time.sleep(_POLL_EVERY)
    return body


def _orch_experiment_ids(orch_id: str) -> list[str]:
    body = requests.get(
        f"{ORCH}/orchestration/{orch_id}/results", timeout=TIMEOUT
    ).json()
    results = body.get("results", [])
    return [r.get("experiment_id") for r in results if r.get("experiment_id")]


def _telemetry_rows(experiment_id: str, retries: int = 4) -> list[dict[str, Any]]:
    """Fetch stored rows for an experiment, briefly retrying while metrics land.

    Telemetry is patched with measured throughput/RTT just after the capture
    finishes, so a freshly-completed run may momentarily show null metrics.
    """
    rows: list[dict[str, Any]] = []
    for attempt in range(retries):
        body = requests.get(
            f"{TELEMETRY}/results",
            params={"experiment_id": experiment_id, "limit": 50},
            timeout=TIMEOUT,
        ).json()
        rows = body.get("results", [])
        if rows and not _is_missing(rows[0].get("measured_throughput")):
            break
        if attempt < retries - 1:
            time.sleep(3)
    return rows


# ── Public API ───────────────────────────────────────────────────────────────
def run_and_display(intent: str) -> None:
    """Submit an intent, wait for it to finish, and print a plain-English summary.

    Works for a single experiment or many (parameter sweeps / concurrent
    multi-app runs) — every experiment the intent produces gets its own block.
    """
    print("Submitting intent to Pramana ...")
    try:
        orch_id = _submit_intent(intent)
    except requests.RequestException as exc:
        print(f"✗ Could not reach the orchestration service at {ORCH}")
        print(f"  {exc}")
        print("  Is the stack running?  (make up)")
        return

    print(f"  orchestration_id: {orch_id}")
    print("  running (shaping + capture + transfer can take a few minutes) ...")
    status_body = _poll(orch_id)
    status = status_body.get("status")

    if status not in {"complete", "completed"}:
        error = status_body.get("error") or "no error message returned"
        print("\n✗ Experiment failed")
        print(f"  reason: {error}")
        if isinstance(error, str) and "decide" in error:
            print(
                "  hint: this application has no matching workflow in the library, "
                "so the orchestrator tried to generate one — a path with a known "
                "bug. Use an app that has a library workflow (e.g. wget/youtube)."
            )
        return

    experiment_ids = _orch_experiment_ids(orch_id)
    if not experiment_ids:
        print("\n✓ Orchestration complete, but no experiment results were recorded.")
        return

    print()
    multi = len(experiment_ids) > 1
    if multi:
        print(f"✓ {len(experiment_ids)} experiments complete\n")

    for idx, exp_id in enumerate(experiment_ids, start=1):
        rows = _telemetry_rows(exp_id)
        row = rows[0] if rows else {}
        app = _app_name(exp_id)

        header = f"✓ Experiment {idx} complete" if multi else "✓ Experiment complete"
        print(header)
        print(f"  App:        {app}")
        print(f"  Capacity:   {_measure(row.get('configured_capacity'), 'Mbps')}")
        print(f"  Latency:    {_measure(row.get('configured_latency'), 'ms', 0)}")
        print(f"  Throughput: {_measure(row.get('measured_throughput'), 'Mbps')}")
        print(f"  RTT:        {_measure(row.get('measured_rtt'), 'ms', 0)}")
        if not rows:
            print("  (metrics not yet available in telemetry)")
        if multi and idx != len(experiment_ids):
            print()


def show_history(limit: int = 15, application: str | None = None) -> Any:
    """Show a clean table of recent experiments recorded in telemetry.

    Pass ``application="browser"`` (or ``"shell"``) to filter; omit it for the
    most recent results across everything.
    """
    params: dict[str, Any] = {
        "limit": limit,
        "sort_by": "created_at",
        "sort_order": "desc",
    }
    if application:
        params["application"] = application

    body = requests.get(f"{TELEMETRY}/results", params=params, timeout=TIMEOUT).json()
    rows = body.get("results", [])

    if not rows:
        print("No experiments recorded in telemetry yet.")
        return None

    friendly = []
    for r in rows:
        friendly.append(
            {
                "when": (r.get("created_at") or "")[:19].replace("T", " "),
                "app": _app_name(r.get("experiment_id"), r.get("application") or "?"),
                "status": r.get("status"),
                "capacity (Mbps)": _num(r.get("configured_capacity")),
                "latency (ms)": _num(r.get("configured_latency")),
                "throughput (Mbps)": _num(r.get("measured_throughput")),
                "rtt (ms)": _num(r.get("measured_rtt")),
            }
        )

    print(f"{len(friendly)} most recent experiment(s) in telemetry:")
    if pd is not None:
        df = pd.DataFrame(friendly)
        display(df)
        return df

    for row in friendly:  
        print("  ", row)
    return friendly
