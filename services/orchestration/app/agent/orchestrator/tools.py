"""Tool definitions and execution for the Orchestrator Agent.

Each tool maps to one or more downstream service API calls via
:class:`~app.engine.executor.DownstreamClients`.  The Anthropic tool schema
is built here so the agent module only needs to import ``TOOLS`` (the schema
list) and ``execute_tool`` (the dispatcher).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from app.engine.executor import DownstreamClients

# ---------------------------------------------------------------------------
# Anthropic tool-use schema declarations
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_experiment",
        "description": (
            "Design and dispatch a single experiment iteration against a substrate "
            "worker.  This applies traffic shaping (capacity, latency, AQM), sets the "
            "congestion-control algorithm, starts a pcap capture, and executes the "
            "requested application workflow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {
                    "type": "string",
                    "description": "Unique experiment identifier.",
                },
                "capacity_mbps": {
                    "type": "number",
                    "description": "Download link capacity in Mbps.",
                },
                "upload_mbps": {
                    "type": "number",
                    "description": "Upload link capacity in Mbps.  Defaults to capacity_mbps if omitted.",
                },
                "latency_ms": {
                    "type": "number",
                    "description": "Added network latency in milliseconds.",
                },
                "application": {
                    "type": "string",
                    "description": "Target application workflow (e.g. youtube, ndt, ping, iperf3, wget).",
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "Experiment duration in seconds.",
                },
                "num_trials": {
                    "type": "integer",
                    "description": "Number of repeated trials.",
                },
                "cc_algorithm": {
                    "type": "string",
                    "description": "Congestion control algorithm (cubic, bbr, reno, htcp, vegas, bic).",
                },
                "aqm_policy": {
                    "type": "string",
                    "description": "Queue discipline / AQM policy (pfifo, codel, pie, fq_codel). Use 'pfifo' for plain drop-tail; 'fifo' is NOT a valid tc qdisc.",
                },
                "ctp_cluster": {
                    "type": "string",
                    "description": "Cross-traffic profile cluster id, or null for no background traffic.",
                },
            },
            "required": ["experiment_id", "capacity_mbps", "latency_ms", "application"],
        },
    },
    {
        "name": "query_results",
        "description": (
            "Query telemetry data for completed experiments.  Filter by experiment_id "
            "or application to retrieve stored results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {
                    "type": "string",
                    "description": "Specific experiment id to fetch.",
                },
                "application": {
                    "type": "string",
                    "description": "Application filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                },
            },
        },
    },
    {
        "name": "validate_ctp",
        "description": (
            "Check whether a cross-traffic profile is valid for a given experiment "
            "configuration.  Returns warnings and matched CTP clusters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capacity_mbps": {
                    "type": "number",
                    "description": "Capacity used to bound candidate intensity.",
                },
                "latency_ms": {
                    "type": "number",
                    "description": "Latency context used for warnings.",
                },
                "ctp_cluster": {
                    "type": "string",
                    "description": "Explicit CTP id to verify.",
                },
            },
        },
    },
    {
        "name": "get_available_applications",
        "description": "List applications supported by the platform (youtube, netflix, zoom, ndt, ping, iperf3, wget, …).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_available_cc_algorithms",
        "description": "List supported congestion-control algorithms.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_experiments",
        "description": "List previously registered experiments and their current status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_service_health",
        "description": (
            "Check the reachability and health of all downstream services "
            "(experiment-api, ctp-service, substrate-worker, telemetry, netgent)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    clients: DownstreamClients | None = None,
) -> dict[str, Any]:
    """Execute a tool call and return the result as a JSON-serializable dict."""
    clients = clients or DownstreamClients()

    if tool_name == "run_experiment":
        return _run_experiment(tool_input, clients)
    if tool_name == "query_results":
        return clients.query_results(tool_input)
    if tool_name == "validate_ctp":
        return _validate_ctp(tool_input, clients)
    if tool_name == "get_available_applications":
        return {
            "applications": [
                "youtube",
                "netflix",
                "zoom",
                "twitch",
                "discord",
                "google-meet",
                "ndt",
                "ping",
                "iperf3",
                "wget",
            ]
        }
    if tool_name == "get_available_cc_algorithms":
        return {"cc_algorithms": ["cubic", "bbr", "reno", "htcp", "vegas", "bic"]}
    if tool_name == "list_experiments":
        return {"experiments": clients.list_experiments()}
    if tool_name == "check_service_health":
        return clients.health()

    raise ValueError(f"Unknown tool: {tool_name}")


def _validate_ctp(
    tool_input: dict[str, Any], clients: DownstreamClients
) -> dict[str, Any]:
    try:
        return clients.validate_ctp_spec(tool_input)
    except Exception as exc:
        return {
            "valid": False,
            "ctp_cluster_id": tool_input.get("ctp_cluster"),
            "warnings": [f"ctp_validate_failed: {exc}"],
            "matches": [],
        }


def _run_experiment(
    tool_input: dict[str, Any], clients: DownstreamClients
) -> dict[str, Any]:
    """Register an experiment, apply shaping, and start a capture."""
    experiment_spec = dict(tool_input)
    exp_id = experiment_spec.get("experiment_id") or f"exp-{uuid.uuid4().hex[:8]}"
    experiment_spec["experiment_id"] = exp_id

    experiment_spec.setdefault("duration_seconds", 60)
    experiment_spec.setdefault("cc_algorithm", "cubic")
    experiment_spec.setdefault("aqm_policy", "fq_codel")
    experiment_spec.setdefault("num_trials", 1)

    capture_iface = os.getenv("SUBSTRATE_CAPTURE_IFACE", "veth2")
    capture_seconds = int(
        os.getenv(
            "ORCH_CAPTURE_DURATION_SECONDS",
            str(min(int(experiment_spec.get("duration_seconds", 60)), 30)),
        )
    )

    shape_payload = {
        "upstream_iface": os.getenv("SUBSTRATE_UPSTREAM_IFACE", "veth4"),
        "downstream_iface": os.getenv("SUBSTRATE_DOWNSTREAM_IFACE", "veth2"),
        "download_mbps": float(experiment_spec["capacity_mbps"]),
        "upload_mbps": float(
            experiment_spec.get("upload_mbps", experiment_spec["capacity_mbps"])
        ),
        "latency_ms": float(experiment_spec["latency_ms"]),
        "latency_location": experiment_spec.get("latency_location", "both"),
        "qdisc": experiment_spec.get("aqm_policy", "fq_codel"),
        "buffer_packets": (
            int(experiment_spec["buffer_packets"])
            if experiment_spec.get("buffer_packets") is not None
            else 1000
        ),
        "qdisc_params": experiment_spec.get(
            "qdisc_params", {"target": "5ms", "interval": "100ms"}
        ),
    }

    capture_payload = {
        "interface": capture_iface,
        "capture_filter": "",
        "filename": exp_id,
        "duration_seconds": capture_seconds,
    }

    experiment_result = clients.run_experiment(experiment_spec)
    shape_result = clients.shape_substrate(shape_payload)
    capture_result = clients.capture_substrate(capture_payload)

    return {
        "status": "dispatched",
        "pipeline": ["experiment_api", "shape", "capture"],
        "experiment": experiment_result,
        "shape": shape_result,
        "capture": capture_result,
    }
