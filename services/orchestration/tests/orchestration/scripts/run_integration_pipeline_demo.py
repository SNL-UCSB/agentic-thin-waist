#!/usr/bin/env python3
"""
Demonstrate cross-service integration used by the orchestration executor.

**Fails fast:** the script stops at the first failed component and prints
diagnostics (HTTP status/body when available). Use ``--verbose`` for tracebacks.

Modes:

  * ``chain`` (default): CTP ``POST /ctps/validate`` → substrate ``POST /shape``
    → ``POST /capture`` (PCAP).

  * ``executor``: ``ToolRouter.run_experiment`` — Experiment API ``POST /experiments``
    → ``/shape`` → ``/capture``.

Environment (same as the service):

  CTP_SERVICE_URL, EXPERIMENT_API_URL, SUBSTRATE_WORKER_URL, SUBSTRATE_*_IFACE,
  ORCH_CAPTURE_DURATION_SECONDS, etc.

Optional:

  --skip-ctp-check     Run chain mode without CTP (only shape → capture); for
                       substrate-only debugging.
  --no-health-check    Skip upfront reachability check.

Activate the project venv first (so ``httpx`` and ``app.*`` imports resolve)::

  source ~/imp_files/virtualenvs/thinwaist/bin/activate
  cd services/orchestration
  pip install -r requirements.txt   # once per venv

Then::

  python scripts/run_integration_pipeline_demo.py
  python scripts/run_integration_pipeline_demo.py --mode executor --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Allow `python scripts/run_integration_pipeline_demo.py` without PYTHONPATH.
_ORCH_ROOT = Path(__file__).resolve().parents[1]
if str(_ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_ORCH_ROOT))

from app.engine.executor import DownstreamClients, ToolRouter  # noqa: E402


def _print(title: str, obj: object) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def _format_exception(exc: BaseException, verbose: bool) -> str:
    parts: list[str] = [f"{type(exc).__name__}: {exc}"]
    r = getattr(exc, "response", None)
    if r is not None:
        parts.append(f"HTTP status: {r.status_code}")
        try:
            body = r.text
            parts.append(f"Response body (truncated):\n{body[:4000]}")
        except Exception as e2:
            parts.append(f"(could not read body: {e2})")
    if verbose:
        parts.append(traceback.format_exc())
    return "\n".join(parts)


def _require_health(
    health: dict[str, str],
    required: tuple[str, ...],
    label: str,
) -> int | None:
    """Return exit code 1 if any required service is unreachable; else None."""
    bad = [name for name in required if health.get(name) != "reachable"]
    if not bad:
        return None
    _print(
        f"Abort: required downstream service(s) unreachable ({label})",
        {
            "unreachable": bad,
            "health": health,
            "hint": "Start the services or set URLs (CTP_SERVICE_URL, SUBSTRATE_WORKER_URL, ...).",
        },
    )
    return 1


def run_chain(
    clients: DownstreamClients,
    *,
    skip_ctp: bool,
    verbose: bool,
) -> int:
    """CTP validate → shape → capture."""
    capacity = float(os.getenv("DEMO_CAPACITY_MBPS", "25"))
    latency = float(os.getenv("DEMO_LATENCY_MS", "50"))

    if not skip_ctp:
        _print(
            "Step 1 — CTP validate (POST /ctps/validate)", "(capacity / cluster lookup)"
        )
        try:
            ctp_out = clients.validate_ctp_spec(
                {"capacity_mbps": capacity, "latency_ms": latency}
            )
            _print("CTP response", ctp_out)
        except Exception as exc:
            _print("CTP validate FAILED — stopping", _format_exception(exc, verbose))
            return 1
    else:
        _print("Step 1 — CTP", "SKIPPED (--skip-ctp-check)")

    shape_payload = {
        "upstream_iface": os.getenv("SUBSTRATE_UPSTREAM_IFACE", "veth4"),
        "downstream_iface": os.getenv("SUBSTRATE_DOWNSTREAM_IFACE", "veth2"),
        "download_mbps": capacity,
        "upload_mbps": float(os.getenv("DEMO_UPLOAD_MBPS", str(capacity))),
        "latency_ms": latency,
        "latency_location": os.getenv("DEMO_LATENCY_LOCATION", "both"),
        "qdisc": os.getenv("DEMO_QDISC", "fq_codel"),
        "buffer_packets": int(os.getenv("DEMO_BUFFER_PACKETS", "1000")),
        "qdisc_params": {"target": "5ms", "interval": "100ms"},
    }
    _print("Step 2 — Substrate shape (POST /shape)", shape_payload)
    try:
        shape_out = clients.shape_substrate(shape_payload)
        _print("Shape response", shape_out)
    except Exception as exc:
        _print("Shape FAILED — stopping", _format_exception(exc, verbose))
        return 1

    cap_sec = int(os.getenv("ORCH_CAPTURE_DURATION_SECONDS", "5"))
    capture_payload = {
        "interface": os.getenv("SUBSTRATE_CAPTURE_IFACE", "veth2"),
        "capture_filter": os.getenv("DEMO_CAPTURE_FILTER", ""),
        "filename": os.getenv("DEMO_PCAP_BASENAME", "integration-pipeline-demo"),
        "duration_seconds": cap_sec,
    }
    _print("Step 3 — Capture / PCAP (POST /capture)", capture_payload)
    try:
        cap_out = clients.capture_substrate(capture_payload)
        _print("Capture started", cap_out)
        cap_id = cap_out.get("capture_id")
        if not cap_id:
            _print("Capture FAILED — no capture_id in response", cap_out)
            return 1
        time.sleep(cap_sec + 0.5)
        st = clients.get_capture(cap_id)
        _print("Capture status after duration", st)
        if st.get("status") != "finished":
            _print(
                "Capture FAILED — expected status 'finished'",
                st,
            )
            return 1
        ec = st.get("exit_code")
        if ec not in (0, None):
            _print("Capture FAILED — tshark exit_code != 0", st)
            return 1
    except Exception as exc:
        _print("Capture FAILED — stopping", _format_exception(exc, verbose))
        return 1

    print("\nDone (chain mode).")
    return 0


def run_executor_tool(
    clients: DownstreamClients,
    *,
    verbose: bool,
) -> int:
    """Same sequence as ToolRouter._run_experiment: experiment → shape → capture."""
    exp_id = os.getenv("DEMO_EXPERIMENT_ID", f"demo-executor-{int(time.time())}")
    spec = {
        "experiment_id": exp_id,
        "capacity_mbps": float(os.getenv("DEMO_CAPACITY_MBPS", "25")),
        "latency_ms": float(os.getenv("DEMO_LATENCY_MS", "50")),
        "application": os.getenv("DEMO_APPLICATION", "youtube"),
        "duration_seconds": int(os.getenv("ORCH_CAPTURE_DURATION_SECONDS", "5")),
        "num_trials": 1,
        "aqm_policy": os.getenv("DEMO_QDISC", "fq_codel"),
    }
    _print(
        "ToolRouter.run_experiment (POST /experiments → /shape → /capture)",
        spec,
    )
    router = ToolRouter(clients=clients)
    try:
        out = router.handle_tool_call("run_experiment", spec)
        _print("Dispatch result", out)
    except Exception as exc:
        _print("run_experiment FAILED — stopping", _format_exception(exc, verbose))
        return 1

    cap_id = (out.get("capture") or {}).get("capture_id")
    if not cap_id:
        _print("FAILED — no capture_id on dispatch result", out)
        return 1
    time.sleep(int(spec["duration_seconds"]) + 0.5)
    try:
        st = clients.get_capture(cap_id)
        _print("Capture status", st)
        if st.get("status") != "finished":
            _print("FAILED — capture did not finish", st)
            return 1
        ec = st.get("exit_code")
        if ec not in (0, None):
            _print("FAILED — tshark exit_code != 0", st)
            return 1
    except Exception as exc:
        _print("get_capture FAILED", _format_exception(exc, verbose))
        return 1

    print("\nDone (executor mode).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("chain", "executor"),
        default="chain",
        help="chain: CTP→shape→capture; executor: ToolRouter (exp API→shape→capture)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include Python tracebacks on errors",
    )
    parser.add_argument(
        "--skip-ctp-check",
        action="store_true",
        help="Chain mode only: skip CTP validate (debug substrate only)",
    )
    parser.add_argument(
        "--no-health-check",
        action="store_true",
        help="Do not abort early when health check shows unreachable services",
    )
    args = parser.parse_args()

    clients = DownstreamClients()
    health = clients.health()
    _print("Downstream health (quick check)", health)

    if not args.no_health_check:
        if args.mode == "chain":
            required: tuple[str, ...] = ("substrate_worker",)
            if not args.skip_ctp_check:
                required = ("ctp_service", "substrate_worker")
            code = _require_health(health, required, "chain mode")
            if code is not None:
                return code
        else:
            code = _require_health(
                health,
                ("experiment_api", "substrate_worker"),
                "executor mode",
            )
            if code is not None:
                return code

    if args.mode == "chain":
        return run_chain(
            clients,
            skip_ctp=args.skip_ctp_check,
            verbose=args.verbose,
        )
    return run_executor_tool(
        clients,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
