"""
Helper functions for the Pramana demo notebook.

Everything the notebook needs — service URLs, HTTP calls, the polling loop,
telemetry queries, and result formatting is in here so the notebook stays simple.

Public API (imported via ``from pramana_helpers import *``):
    run_and_display(intent)   submit an intent, wait for it, print a plain-English summary
    show_history()            print a clean table of recent experiments from telemetry
    plot_experiment()         plot per-app throughput + queue depth for the last run
"""

from __future__ import annotations

import glob
import ipaddress
import json
import math
import os
import socket
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


__all__ = ["run_and_display", "show_history", "plot_experiment", "ORCH", "TELEMETRY"]

# ── Service endpoints (local stack) ──────────────────────────────────────────
ORCH = "http://localhost:8005"  # orchestration service
TELEMETRY = "http://localhost:8004"  # telemetry service
TIMEOUT = 30  # per-request timeout (seconds)

# Where the substrate worker writes captures; bind-mounted to the same host path,
# so the notebook can read pcaps/qtraces directly.
CAPTURE_DIR = "/tmp/substrate-capture"

_TERMINAL = {"complete", "completed", "failed"}
_POLL_EVERY = 5  # seconds between status polls
_MAX_POLLS = 360  # generous cap (~30 min) for sweeps / multi-app / browser runs

# Details of the most recent run, populated by run_and_display() so plot_experiment()
# knows which pcap(s) to analyze without the user passing anything.
_LAST_RUN: dict[str, Any] = {"orch_id": None, "experiments": []}


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


def _parse_experiment_id(experiment_id: str) -> dict[str, Any]:
    """Extract config encoded in experiment_id: {app}_{dl}_{ul}_{lat}_{qdisc}_{cc}_{hash}.

    Returns whatever we can parse; missing fields are None.
    """
    parts = experiment_id.rsplit("_", 1)
    if len(parts) < 2:
        return {"app": experiment_id}
    body = parts[0]
    tokens = body.split("_")
    result: dict[str, Any] = {"app": tokens[0] if tokens else experiment_id}
    try:
        result["capacity_mbps"] = float(tokens[1]) if len(tokens) > 1 else None
    except (ValueError, IndexError):
        result["capacity_mbps"] = None
    try:
        result["latency_ms"] = float(tokens[3]) if len(tokens) > 3 else None
    except (ValueError, IndexError):
        result["latency_ms"] = None
    return result


def _pcap_stats_from_worker(capture_id: str) -> dict[str, Any] | None:
    """Try to fetch throughput/RTT from the substrate worker's /capture/{id}/stats."""
    worker = os.getenv("SUBSTRATE_WORKER_URL", "http://localhost:8002")
    try:
        resp = requests.get(f"{worker}/capture/{capture_id}/stats", timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


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


def _orch_results(orch_id: str) -> list[dict[str, Any]]:
    """Return the authoritative per-experiment results for an orchestration run."""
    body = requests.get(
        f"{ORCH}/orchestration/{orch_id}/results", timeout=TIMEOUT
    ).json()
    return [r for r in body.get("results", []) if r.get("experiment_id")]


def _result_pcap_path(result: dict[str, Any]) -> str | None:
    """Pull the pcap path out of a result (top-level or nested capture_status)."""
    return (
        result.get("pcap_path")
        or (result.get("capture_status") or {}).get("pcap_path")
        or (result.get("capture") or {}).get("pcap_path")
    )


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

    results = _orch_results(orch_id)
    experiment_ids = [r["experiment_id"] for r in results]
    if not experiment_ids:
        print("\n✓ Orchestration complete, but no experiment results were recorded.")
        return

    # Remember this run so plot_experiment() can find the pcap(s) automatically.
    _LAST_RUN["orch_id"] = orch_id
    _LAST_RUN["experiments"] = []

    print()
    multi = len(experiment_ids) > 1
    if multi:
        print(f"✓ {len(experiment_ids)} experiments complete\n")

    for idx, result in enumerate(results, start=1):
        exp_id = result["experiment_id"]
        rows = _telemetry_rows(exp_id)
        row = rows[0] if rows else {}
        app = _app_name(exp_id)

        # Primary source: telemetry row.  Fallback: parse the experiment_id
        # (which encodes capacity/latency) and fetch pcap stats from the worker.
        parsed = _parse_experiment_id(exp_id)
        capacity = row.get("configured_capacity") or parsed.get("capacity_mbps")
        latency = row.get("configured_latency") or parsed.get("latency_ms")
        throughput = row.get("measured_throughput")
        rtt = row.get("measured_rtt")

        if _is_missing(throughput):
            cap_id = (result.get("capture_status") or result.get("capture") or {}).get(
                "capture_id"
            )
            if cap_id:
                stats = _pcap_stats_from_worker(cap_id)
                if stats and stats.get("throughput_mbps"):
                    # Only use pcap stats if the capture was non-empty (>0 Mbps).
                    throughput = stats.get("throughput_mbps")
                    rtt = stats.get("rtt_ms") if _is_missing(rtt) else rtt

        _LAST_RUN["experiments"].append(
            {
                "experiment_id": exp_id,
                "app": app,
                "capacity_mbps": capacity,
                "pcap_path": _result_pcap_path(result),
            }
        )

        header = f"✓ Experiment {idx} complete" if multi else "✓ Experiment complete"
        print(header)
        print(f"  App:        {app}")
        print(f"  Capacity:   {_measure(capacity, 'Mbps')}")
        print(f"  Latency:    {_measure(latency, 'ms', 0)}")
        print(f"  Throughput: {_measure(throughput, 'Mbps')}")
        print(f"  RTT:        {_measure(rtt, 'ms', 0)}")
        if not rows and _is_missing(throughput):
            print("  (metrics not yet available)")
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


# ── PCAP / qtrace time-series plotting ───────────────────────────────────────
def _open_pcap(path: str):
    """Open a capture with the right scapy reader (pcapng vs classic pcap)."""
    from scapy.utils import PcapNgReader, PcapReader

    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic == b"\x0a\x0d\x0d\x0a":  # pcapng section-header magic
        return PcapNgReader(path)
    return PcapReader(path)


def _remote_ip(src: str, dst: str) -> str:
    """Return the public (server-side) address of a packet, else the dst.

    On the shaped veth path both directions of a flow share the same private
    client IP, so grouping by the *public* endpoint is what separates one app's
    server from another's.
    """
    for ip in (src, dst):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            return ip
    return dst


def _rdns(ip: str) -> str | None:
    """Best-effort reverse DNS with a short timeout (hint for which app)."""
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(1.0)
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(old)


def _extract_ips(pkt) -> tuple[str, str] | None:
    """Return (src_ip, dst_ip) for a packet, decoding raw frames if needed.

    The worker captures veth (Ethernet) traffic, but scapy's PcapNgReader can
    hand back undissected ``Raw`` packets (the pcapng interface link type isn't
    always mapped). We re-decode the raw bytes as Ethernet, then fall back to a
    bare IP/IPv6 header, so per-flow attribution works regardless.
    """
    from scapy.layers.inet import IP
    from scapy.layers.inet6 import IPv6
    from scapy.layers.l2 import Ether

    if pkt.haslayer("IP"):
        return pkt["IP"].src, pkt["IP"].dst
    if pkt.haslayer("IPv6"):
        return pkt["IPv6"].src, pkt["IPv6"].dst

    raw = bytes(pkt)
    try:
        eth = Ether(raw)
        if eth.haslayer(IP):
            return eth[IP].src, eth[IP].dst
        if eth.haslayer(IPv6):
            return eth[IPv6].src, eth[IPv6].dst
    except Exception:
        pass
    if raw:
        version = raw[0] >> 4
        try:
            if version == 4:
                ip = IP(raw)
                return ip.src, ip.dst
            if version == 6:
                ip6 = IPv6(raw)
                return ip6.src, ip6.dst
        except Exception:
            pass
    return None


def _pcap_throughput_by_ip(pcap_path: str, top_n: int):
    """Return (times, {ip: mbps_per_sec}, {ip: total_bytes}) from a capture."""
    buckets: dict[str, dict[int, int]] = {}
    totals: dict[str, int] = {}
    t0: float | None = None
    max_sec = 0

    reader = _open_pcap(pcap_path)
    try:
        for pkt in reader:
            try:
                ts = float(pkt.time)
            except Exception:
                continue
            ips = _extract_ips(pkt)
            if ips is None:
                continue
            if t0 is None:
                t0 = ts
            sec = max(0, int(ts - t0))
            max_sec = max(max_sec, sec)
            ip = _remote_ip(ips[0], ips[1])
            length = len(pkt)
            buckets.setdefault(ip, {})[sec] = buckets.get(ip, {}).get(sec, 0) + length
            totals[ip] = totals.get(ip, 0) + length
    finally:
        try:
            reader.close()
        except Exception:
            pass

    top = sorted(totals, key=lambda k: totals[k], reverse=True)[:top_n]
    times = list(range(max_sec + 1))
    series = {ip: [buckets[ip].get(s, 0) * 8 / 1e6 for s in times] for ip in top}
    return [float(t) for t in times], series, totals


def _read_qtrace(qtrace_path: str) -> dict[str, dict[str, list]]:
    """Return {iface: {"t": [...], "pkts": [...], "bytes": [...]}} from qtrace JSONL."""
    data: dict[str, dict[str, list]] = {}
    t0: float | None = None
    with open(qtrace_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = sample.get("t")
            iface = sample.get("iface")
            if t is None or iface is None:
                continue
            if t0 is None:
                t0 = t
            d = data.setdefault(iface, {"t": [], "pkts": [], "bytes": []})
            d["t"].append(t - t0)
            d["pkts"].append(sample.get("backlog_pkts") or 0)
            d["bytes"].append(sample.get("backlog_bytes") or 0)
    return data


def _resolve_experiments() -> list[dict[str, Any]]:
    """Experiments to plot: the last run, else the newest pcap in CAPTURE_DIR."""
    exps = list(_LAST_RUN.get("experiments") or [])
    if exps:
        return exps
    pcaps = sorted(
        glob.glob(os.path.join(CAPTURE_DIR, "*.pcap")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not pcaps:
        return []
    newest = pcaps[0]
    exp_id = os.path.splitext(os.path.basename(newest))[0]
    return [
        {
            "experiment_id": exp_id,
            "app": _app_name(exp_id),
            "capacity_mbps": None,
            "pcap_path": newest,
        }
    ]


def _find_pcap(exp: dict[str, Any]) -> str | None:
    pcap = exp.get("pcap_path")
    if pcap and os.path.isfile(pcap):
        return pcap
    candidate = os.path.join(CAPTURE_DIR, f"{exp['experiment_id']}.pcap")
    return candidate if os.path.isfile(candidate) else None


def _pretty_title(app: str, cap_mbps: float, exp_id: str) -> str:
    """Build a human-readable title from the app name and network config.

    E.g. 'YouTube VOD — 6 Mbps / 50 ms / pfifo / cubic'
    Falls back to the raw experiment_id if parsing fails.
    """
    # Friendly display names for known apps
    _DISPLAY = {
        "youtube": "YouTube",
        "vimeo": "Vimeo",
        "tubi": "Tubi",
        "twitch": "Twitch",
        "zoom": "Zoom",
        "meet": "Google Meet",
        "teams": "Microsoft Teams",
        "netflix": "Netflix",
        "wikipedia": "Wikipedia",
        "googlenews": "Google News",
        "puffer": "Puffer",
        "roku": "Roku",
        "wget": "wget",
        "iperf": "iPerf",
        "ndt": "NDT",
    }
    display_app = _DISPLAY.get(app.lower(), app.title())
    # Parse network params from exp_id: <app>_<dl>_<ul>_<lat>_<qdisc>_<cc>_<hash>
    parts = exp_id.split("_")
    try:
        lat = parts[3]
        qdisc = parts[4]
        cc = parts[5]
        return f"{display_app} — {_num(cap_mbps)} Mbps / {lat} ms / {qdisc} / {cc}"
    except IndexError:
        return f"{display_app} — {_num(cap_mbps)} Mbps"


def _plot_pcap(
    pcap_path: str, cap_mbps: float, top_n: int, title_prefix: str = ""
) -> list[str]:
    import matplotlib.pyplot as plt

    saved: list[str] = []
    root = os.path.splitext(pcap_path)[0]

    # ── Plot 1: throughput over time, one line per (remote) app IP ──
    times, series, totals = _pcap_throughput_by_ip(pcap_path, top_n)
    if times:
        fig, ax = plt.subplots(figsize=(11, 4.5))
        for ip in series:
            host = _rdns(ip)
            legend = f"{ip} ({host})" if host else ip
            ax.plot(times, series[ip], linewidth=1.3, label=legend)
        ax.axhline(
            cap_mbps,
            color="#dc2626",
            linestyle="--",
            linewidth=1.5,
            label=f"{_num(cap_mbps)} Mbps cap",
        )
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Throughput (Mbps)")
        ax.set_title(f"Throughput — {title_prefix}" if title_prefix else "Throughput")
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        out = f"{root}_throughput.png"
        fig.savefig(out, dpi=150)
        saved.append(out)
        plt.show()
        plt.close(fig)
    else:
        print(f"  no IP packets found in {os.path.basename(pcap_path)}")

    # ── Plot 2: queue depth over time (from qtrace JSONL, if present) ──
    qtrace_path = f"{root}_qtrace.jsonl"
    if os.path.isfile(qtrace_path):
        qdata = _read_qtrace(qtrace_path)
        # Prefer interfaces that actually built a backlog.
        active = {
            iface: d for iface, d in qdata.items() if d["pkts"] and max(d["pkts"]) > 0
        } or qdata
        if active:
            fig, ax = plt.subplots(figsize=(11, 4.5))
            for iface, d in active.items():
                ax.plot(d["t"], d["pkts"], linewidth=1.2, label=f"{iface} backlog")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Queue depth (packets)")
            ax.set_title(
                f"Queue depth — {title_prefix}" if title_prefix else "Queue depth"
            )
            ax.set_ylim(bottom=0)
            ax.legend(loc="upper right", fontsize=8)
            fig.tight_layout()
            out = f"{root}_queue_depth.png"
            fig.savefig(out, dpi=150)
            saved.append(out)
            plt.show()
            plt.close(fig)
    else:
        print(
            f"  no qtrace file alongside {os.path.basename(pcap_path)} — skipping queue plot"
        )

    return saved


def plot_experiment(cap_mbps: float | None = None, top_n: int = 6) -> list[str]:
    """Plot per-app throughput and queue depth for the most recent run.

    For each experiment produced by the last ``run_and_display`` call (a single
    pcap for a concurrent multi-app run, or one per experiment for a sweep) this
    reads the pcap from CAPTURE_DIR with scapy, draws:

      1. throughput over time (Mbps/s), one line per remote server IP, with the
         configured capacity marked as a red dashed cap line;
      2. queue depth over time from the qtrace JSONL beside the pcap, if present.

    Both PNGs are saved next to the pcap and shown inline. Returns saved paths.
    """
    exps = _resolve_experiments()
    if not exps:
        print(
            f"No experiment to plot — run_and_display(...) first (looked in {CAPTURE_DIR})."
        )
        return []

    all_saved: list[str] = []
    for exp in exps:
        pcap = _find_pcap(exp)
        print(f"\nExperiment: {exp['experiment_id']}")
        if not pcap:
            print(f"  pcap not found in {CAPTURE_DIR} — skipping")
            continue
        cap = cap_mbps or exp.get("capacity_mbps") or 6.0
        title = _pretty_title(
            exp.get("app") or "experiment", float(cap), exp["experiment_id"]
        )
        print(f"  pcap: {pcap}")
        all_saved.extend(_plot_pcap(pcap, float(cap), top_n, title_prefix=title))

    if all_saved:
        print("\nSaved:")
        for path in all_saved:
            print(f"  {path}")
    return all_saved
