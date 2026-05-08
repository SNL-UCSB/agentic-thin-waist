"""Pcap parsing and time-series plotting helpers.

All functions accept either a path to a .pcap/.pcapng file or a list of scapy
packets. Plotting helpers return the matplotlib Axes so the caller can
customize titles, save the figure, etc.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from scapy.all import ICMP, IP, TCP, UDP, IPv6, rdpcap


def load_pcap(path: str | Path):
    return rdpcap(str(path))


def _as_packets(pkts_or_path):
    if isinstance(pkts_or_path, (str, Path)):
        return load_pcap(pkts_or_path)
    return pkts_or_path


def _flow_key(p) -> Optional[tuple]:
    """5-tuple key, direction-normalized so A↔B flows collapse to one bucket."""
    if IP in p:
        src, dst = p[IP].src, p[IP].dst
    elif IPv6 in p:
        src, dst = p[IPv6].src, p[IPv6].dst
    else:
        return None
    if TCP in p:
        proto, sp, dp = "tcp", p[TCP].sport, p[TCP].dport
    elif UDP in p:
        proto, sp, dp = "udp", p[UDP].sport, p[UDP].dport
    else:
        return None
    a, b = (src, sp), (dst, dp)
    lo, hi = (a, b) if a <= b else (b, a)
    return (proto, lo, hi)


def throughput_timeseries(
    pkts_or_path,
    bin_seconds: float = 0.1,
    unit: str = "mbps",
) -> tuple[list[float], list[float]]:
    """Aggregate total bytes per time bin → (t_seconds, rate).

    `unit` ∈ {"bps", "kbps", "mbps", "Bps"}.
    Times are seconds since the first packet.
    """
    pkts = _as_packets(pkts_or_path)
    if not pkts:
        return [], []
    t0 = float(pkts[0].time)
    bins: dict[int, int] = defaultdict(int)
    last = 0
    for p in pkts:
        idx = int((float(p.time) - t0) / bin_seconds)
        bins[idx] += len(p)
        if idx > last:
            last = idx
    factors = {"bps": 8.0, "kbps": 8e-3, "mbps": 8e-6, "Bps": 1.0}
    f = factors.get(unit, factors["mbps"])
    xs = [i * bin_seconds for i in range(last + 1)]
    ys = [bins[i] * f / bin_seconds for i in range(last + 1)]
    return xs, ys


def icmp_rtt_pairs(pkts_or_path) -> list[tuple[float, float]]:
    """Match ICMP echo-request/echo-reply by (id, seq) → list of (t_since_first, rtt_ms)."""
    pkts = _as_packets(pkts_or_path)
    pending: dict[tuple[int, int], float] = {}
    pairs: list[tuple[float, float]] = []
    for p in pkts:
        if ICMP not in p or p[ICMP].type not in (8, 0):
            continue
        icmp = p[ICMP]
        k = (int(icmp.id), int(icmp.seq))
        t = float(p.time)
        if icmp.type == 8:
            pending[k] = t
        elif k in pending:
            pairs.append((t, t - pending.pop(k)))
    pairs.sort(key=lambda x: x[0])
    if not pairs:
        return []
    t0 = pairs[0][0]
    return [(t - t0, dt * 1000.0) for t, dt in pairs]


def tcp_flows(pkts_or_path) -> dict[tuple, dict[str, Any]]:
    """Group TCP packets by direction-normalized 5-tuple. Returns

        {flow_key: {"packets": int, "bytes": int, "first_ts": float, "last_ts": float}}
    """
    pkts = _as_packets(pkts_or_path)
    out: dict[tuple, dict[str, Any]] = {}
    for p in pkts:
        k = _flow_key(p)
        if k is None or k[0] != "tcp":
            continue
        rec = out.setdefault(
            k,
            {"packets": 0, "bytes": 0, "first_ts": float(p.time), "last_ts": float(p.time)},
        )
        rec["packets"] += 1
        rec["bytes"] += len(p)
        rec["last_ts"] = float(p.time)
    return out


def summarize_pcap(pkts_or_path) -> dict[str, Any]:
    pkts = _as_packets(pkts_or_path)
    n = len(pkts)
    if n == 0:
        return {"packets": 0}
    total_bytes = sum(len(p) for p in pkts)
    t_first, t_last = float(pkts[0].time), float(pkts[-1].time)
    duration = max(t_last - t_first, 1e-9)
    proto = {"tcp": 0, "udp": 0, "icmp": 0, "other": 0}
    for p in pkts:
        if TCP in p:
            proto["tcp"] += 1
        elif UDP in p:
            proto["udp"] += 1
        elif ICMP in p:
            proto["icmp"] += 1
        else:
            proto["other"] += 1
    return {
        "packets": n,
        "total_bytes": total_bytes,
        "duration_s": duration,
        "avg_throughput_mbps": total_bytes * 8e-6 / duration,
        "protocols": proto,
        "tcp_flows": len(tcp_flows(pkts)),
    }


# --------------------------------------------------------------------------- #
# Plotting
# --------------------------------------------------------------------------- #

def _ensure_ax(ax):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(11, 4))
    return ax


def plot_throughput(
    pkts_or_path,
    bin_seconds: float = 0.1,
    unit: str = "mbps",
    ax=None,
    title: Optional[str] = None,
):
    ax = _ensure_ax(ax)
    xs, ys = throughput_timeseries(pkts_or_path, bin_seconds=bin_seconds, unit=unit)
    ax.plot(xs, ys, linewidth=1.0)
    ax.set_xlabel("time since first packet (s)")
    ax.set_ylabel(f"throughput ({unit})")
    ax.set_title(title or f"Throughput — bin={bin_seconds}s")
    ax.grid(alpha=0.3)
    return ax


def plot_icmp_rtt(pkts_or_path, ax=None, title: Optional[str] = None):
    ax = _ensure_ax(ax)
    pairs = icmp_rtt_pairs(pkts_or_path)
    if not pairs:
        ax.text(0.5, 0.5, "no ICMP echo pairs", ha="center", va="center")
        ax.set_axis_off()
        return ax
    xs = [t for t, _ in pairs]
    ys = [r for _, r in pairs]
    ax.plot(xs, ys, marker="o", markersize=2, linewidth=0.8)
    ax.set_xlabel("time since first reply (s)")
    ax.set_ylabel("RTT (ms)")
    ax.set_title(title or f"ICMP RTT — {len(pairs)} samples")
    ax.grid(alpha=0.3)
    return ax


def plot_packet_size(pkts_or_path, ax=None, title: Optional[str] = None):
    ax = _ensure_ax(ax)
    pkts = _as_packets(pkts_or_path)
    if not pkts:
        ax.set_axis_off()
        return ax
    t0 = float(pkts[0].time)
    xs = [float(p.time) - t0 for p in pkts]
    ys = [len(p) for p in pkts]
    ax.scatter(xs, ys, s=4, alpha=0.5)
    ax.set_xlabel("time since first packet (s)")
    ax.set_ylabel("packet size (bytes)")
    ax.set_title(title or "Per-packet size over time")
    ax.grid(alpha=0.3)
    return ax
