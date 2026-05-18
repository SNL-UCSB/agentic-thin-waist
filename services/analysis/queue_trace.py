"""Load and plot queue-occupancy traces produced by `POST /qtrace`.

Each line in the JSONL trace is one snapshot of one leaf qdisc:

    {"t": 1716000000.123, "iface": "veth2",
     "backlog_bytes": 12345, "backlog_pkts": 12,
     "bytes_sent": ..., "pkts_sent": ..., "drops": 0, "overlimits": 0}

This module provides:
  - ``load_queue_trace(path)``     → ``pandas.DataFrame``
  - ``plot_queue_occupancy(df)``   → matplotlib plot of backlog vs time
  - ``plot_drop_rate(df)``         → drop-rate (per-bin) vs time
  - ``summarize_queue_trace(df)``  → dict with min/mean/max/p50/p95/p99 backlog
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - guard for environments without pandas
    raise ImportError(
        "services/analysis/queue_trace.py requires pandas. "
        "Run `pip install pandas` in the analysis environment."
    ) from exc


def load_queue_trace(path: str | Path) -> "pd.DataFrame":
    """Read a JSONL queue trace into a DataFrame indexed by relative time.

    Adds two convenience columns:
      - ``rel_t``  : seconds since the first sample
      - ``drops_rate_per_s`` : drops/sec computed by diffing the cumulative
        ``drops`` counter against the previous sample for the same interface.
    """
    rows: list[dict[str, Any]] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return pd.DataFrame(
            columns=[
                "t",
                "iface",
                "backlog_bytes",
                "backlog_pkts",
                "bytes_sent",
                "pkts_sent",
                "drops",
                "overlimits",
            ]
        )

    df = pd.DataFrame(rows)
    df["t"] = pd.to_numeric(df["t"], errors="coerce")
    df = df.dropna(subset=["t"]).sort_values("t").reset_index(drop=True)
    t0 = df["t"].min()
    df["rel_t"] = df["t"] - t0

    # Per-interface drop and byte rates (kernel counters are cumulative).
    df = df.sort_values(["iface", "t"]).reset_index(drop=True)
    df["drops_delta"] = (
        df.groupby("iface")["drops"].diff().clip(lower=0).fillna(0)
    )
    df["bytes_sent_delta"] = (
        df.groupby("iface")["bytes_sent"].diff().clip(lower=0).fillna(0)
    )
    df["t_delta"] = df.groupby("iface")["t"].diff().fillna(0)
    df["drops_rate_per_s"] = (
        df["drops_delta"] / df["t_delta"].replace(0, float("nan"))
    ).fillna(0)
    df["throughput_mbps_from_qdisc"] = (
        df["bytes_sent_delta"] * 8 / 1e6 / df["t_delta"].replace(0, float("nan"))
    ).fillna(0)

    return df.sort_values("t").reset_index(drop=True)


def summarize_queue_trace(df: "pd.DataFrame") -> dict[str, Any]:
    """Summary statistics keyed by interface."""
    if df.empty:
        return {}
    out: dict[str, Any] = {}
    for iface, sub in df.groupby("iface"):
        bp = sub["backlog_pkts"].dropna()
        bb = sub["backlog_bytes"].dropna()
        out[str(iface)] = {
            "samples": int(len(sub)),
            "duration_s": float(sub["rel_t"].max() - sub["rel_t"].min()),
            "backlog_pkts": {
                "min": float(bp.min()) if len(bp) else 0.0,
                "mean": float(bp.mean()) if len(bp) else 0.0,
                "p50": float(bp.quantile(0.50)) if len(bp) else 0.0,
                "p95": float(bp.quantile(0.95)) if len(bp) else 0.0,
                "p99": float(bp.quantile(0.99)) if len(bp) else 0.0,
                "max": float(bp.max()) if len(bp) else 0.0,
            },
            "backlog_bytes": {
                "min": float(bb.min()) if len(bb) else 0.0,
                "mean": float(bb.mean()) if len(bb) else 0.0,
                "p95": float(bb.quantile(0.95)) if len(bb) else 0.0,
                "max": float(bb.max()) if len(bb) else 0.0,
            },
            "total_drops": int(sub["drops_delta"].sum()),
            "mean_throughput_mbps": float(
                sub["throughput_mbps_from_qdisc"].mean()
            ),
        }
    return out


def plot_queue_occupancy(
    df: "pd.DataFrame",
    *,
    unit: str = "packets",
    ifaces: Optional[Iterable[str]] = None,
    ax=None,
    title: Optional[str] = None,
):
    """Plot bottleneck queue depth over time, one line per interface.

    Args:
        df: DataFrame from :func:`load_queue_trace`.
        unit: ``"packets"`` (default) or ``"bytes"``.
        ifaces: subset of interfaces to plot (default: all present).
        ax: matplotlib axis to draw into (creates one if None).
        title: chart title.
    """
    import matplotlib.pyplot as plt

    if df.empty:
        raise ValueError("queue trace is empty")

    column = "backlog_pkts" if unit == "packets" else "backlog_bytes"
    if column not in df.columns:
        raise ValueError(f"trace is missing column {column!r}")

    if ax is None:
        _, ax = plt.subplots(figsize=(12, 4))

    targets = list(ifaces) if ifaces is not None else sorted(df["iface"].unique())
    for iface in targets:
        sub = df[df["iface"] == iface]
        ax.plot(
            sub["rel_t"],
            sub[column],
            label=iface,
            linewidth=0.9,
        )
    ax.set_xlabel("time since trace start (s)")
    ax.set_ylabel(f"queue occupancy ({unit})")
    ax.set_title(title or "Bottleneck queue occupancy")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    return ax


def plot_drop_rate(
    df: "pd.DataFrame",
    *,
    ifaces: Optional[Iterable[str]] = None,
    ax=None,
    title: Optional[str] = None,
):
    """Plot per-interface drop rate (packets/sec) over time."""
    import matplotlib.pyplot as plt

    if df.empty:
        raise ValueError("queue trace is empty")

    if ax is None:
        _, ax = plt.subplots(figsize=(12, 3))

    targets = list(ifaces) if ifaces is not None else sorted(df["iface"].unique())
    for iface in targets:
        sub = df[df["iface"] == iface]
        ax.plot(sub["rel_t"], sub["drops_rate_per_s"], label=iface, linewidth=0.9)
    ax.set_xlabel("time since trace start (s)")
    ax.set_ylabel("drops/sec")
    ax.set_title(title or "Drop rate")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    return ax
