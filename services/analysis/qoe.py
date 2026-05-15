"""Pretty-printers and extractors for ExperimentResult QoE / transport / context.

The telemetry service stores `qoe_metrics` as flexible JSON, so the format
depends on what produced the result (speedtest, iperf, ping, youtube, ...).
The helpers here normalize a few common shapes plus a generic dump.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional


def _kv(d: dict[str, Any], indent: int = 2) -> str:
    if not d:
        return " " * indent + "(empty)"
    return "\n".join(f"{' ' * indent}{k}: {v}" for k, v in d.items())


def _dump_json(obj: Any, indent: int = 2) -> str:
    return json.dumps(obj, indent=indent, default=str, sort_keys=False)


# --------------------------------------------------------------------------- #
# Pretty-printers
# --------------------------------------------------------------------------- #


def print_result_summary(result: dict[str, Any]) -> None:
    """One-line-ish summary header followed by all four-layer context."""
    rid = result.get("result_id", "?")
    eid = result.get("experiment_id", "?")
    trial = result.get("trial_number", "?")
    status = result.get("status", "?")
    created = result.get("created_at", "?")
    print(f"result_id      : {rid}")
    print(f"experiment_id  : {eid}")
    print(f"trial_number   : {trial}")
    print(f"status         : {status}")
    print(f"created_at     : {created}")
    bs = result.get("bottleneck_state") or {}
    if bs:
        print("bottleneck_state:")
        print(_kv(bs))
    print()
    print_contextual_tree(result.get("contextual_tree") or {})


def print_qoe_metrics(result: dict[str, Any]) -> None:
    """Dump qoe_metrics as JSON (most reliable since shape varies per workflow)."""
    qoe = result.get("qoe_metrics") or {}
    print("qoe_metrics:")
    print(_dump_json(qoe))


def print_transport_state(result: dict[str, Any]) -> None:
    ts = result.get("transport_state") or {}
    print("transport_state:")
    print(_dump_json(ts))


def print_contextual_tree(tree: dict[str, Any]) -> None:
    print("contextual_tree:")
    for layer in ("c_static", "c_dyn", "c_app", "c_trans"):
        section = tree.get(layer) or {}
        print(f"  {layer}:")
        print(_kv(section, indent=4))


# --------------------------------------------------------------------------- #
# Workflow-specific extractors. Each returns a flat dict of "interesting"
# fields if the qoe_metrics looks like that workflow, else {}.
# --------------------------------------------------------------------------- #


def _first_present(d: dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def extract_speedtest(result: dict[str, Any]) -> dict[str, Any]:
    """Pull download/upload/latency fields from a speedtest-shaped qoe_metrics.

    Tolerates the common shapes:
      - {"download_mbps": ..., "upload_mbps": ..., "latency_ms": ...}
      - {"download": {"bandwidth": bytes/s}, "upload": {...}, "ping": {...}}  (speedtest-cli json)
      - NDT result objects with `.download` / `.upload` blocks
    """
    qoe = result.get("qoe_metrics") or {}
    out: dict[str, Any] = {}

    out["download_mbps"] = _first_present(
        qoe, ["download_mbps", "download_speed_mbps", "downloadMbps"]
    )
    out["upload_mbps"] = _first_present(
        qoe, ["upload_mbps", "upload_speed_mbps", "uploadMbps"]
    )
    out["latency_ms"] = _first_present(qoe, ["latency_ms", "ping_ms", "rtt_ms"])
    out["jitter_ms"] = _first_present(qoe, ["jitter_ms", "jitter"])
    out["packet_loss_pct"] = _first_present(qoe, ["packet_loss_pct", "packet_loss"])

    dl = qoe.get("download") if isinstance(qoe.get("download"), dict) else None
    ul = qoe.get("upload") if isinstance(qoe.get("upload"), dict) else None
    ping = qoe.get("ping") if isinstance(qoe.get("ping"), dict) else None
    if dl and out["download_mbps"] is None:
        bw = _first_present(dl, ["bandwidth", "throughput", "mbps"])
        if isinstance(bw, (int, float)):
            out["download_mbps"] = bw / 125_000 if bw > 1e4 else bw
    if ul and out["upload_mbps"] is None:
        bw = _first_present(ul, ["bandwidth", "throughput", "mbps"])
        if isinstance(bw, (int, float)):
            out["upload_mbps"] = bw / 125_000 if bw > 1e4 else bw
    if ping and out["latency_ms"] is None:
        out["latency_ms"] = _first_present(ping, ["latency", "rtt", "avg"])

    return {k: v for k, v in out.items() if v is not None}


def extract_iperf(result: dict[str, Any]) -> dict[str, Any]:
    qoe = result.get("qoe_metrics") or {}
    out: dict[str, Any] = {}

    out["throughput_mbps"] = _first_present(
        qoe, ["throughput_mbps", "bitrate_mbps", "mean_throughput_mbps"]
    )
    out["retransmits"] = _first_present(qoe, ["retransmits", "retx", "retransmissions"])
    out["jitter_ms"] = _first_present(qoe, ["jitter_ms", "jitter"])
    out["lost_packets"] = _first_present(qoe, ["lost_packets", "packets_lost"])

    end = qoe.get("end") if isinstance(qoe.get("end"), dict) else None
    if end:
        sent = end.get("sum_sent") or {}
        if out["throughput_mbps"] is None and "bits_per_second" in sent:
            out["throughput_mbps"] = sent["bits_per_second"] / 1e6
        if out["retransmits"] is None and "retransmits" in sent:
            out["retransmits"] = sent["retransmits"]

    return {k: v for k, v in out.items() if v is not None}


def extract_ping(result: dict[str, Any]) -> dict[str, Any]:
    qoe = result.get("qoe_metrics") or {}
    keys = [
        "min_rtt_ms",
        "avg_rtt_ms",
        "max_rtt_ms",
        "stddev_rtt_ms",
        "packet_loss_pct",
        "transmitted",
        "received",
    ]
    return {k: qoe[k] for k in keys if k in qoe and qoe[k] is not None}
