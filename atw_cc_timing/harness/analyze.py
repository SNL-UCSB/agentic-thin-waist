#!/usr/bin/env python3
"""Analyze the 20-run phase-resolved timing + tokens and render figures
(cc_queue/cc_plots style). Run after aggregate.py.

Outputs (in atw_cc_timing/):
  fig_phase_stacked.png    per-run stacked phase breakdown (compile/spin-up/transfer/drain)
  fig_phase_stats.png      median + p10/p90 per phase (bar w/ error bars)
  fig_overhead_cdf.png     CDF of orchestration overhead (wall - transfer)
  fig_tokens.png           per-intent parse token cost
  fig_queue_gallery.png    bottleneck queue-occupancy traces for collected runs
"""
import glob
import json
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TROOT = "/home/jaber/agentic-thin-waist/atw_cc_timing"
plt.rcParams.update({"figure.dpi": 120, "axes.grid": True, "grid.alpha": 0.3,
                     "savefig.bbox": "tight", "font.size": 10})

PAPER_NAME = {
    "reno": "NewReno", "cubic": "Cubic", "bbr": "BBR", "bic": "BIC", "cdg": "CDG",
    "highspeed": "Highspeed", "htcp": "HTCP", "hybla": "Hybla", "illinois": "Illinois",
    "nv": "New Vegas", "scalable": "Scalable", "vegas": "Vegas", "veno": "Veno",
    "westwood": "Westwood", "yeah": "Yeah",
}

t = pd.read_csv(f"{TROOT}/timing.csv", comment="#")
ok = t[t["final_status"] == "complete"].copy().reset_index(drop=True)
print(f"loaded {len(t)} runs, {len(ok)} complete")

# ---- 1. per-run stacked phase breakdown ----
STACK = [("compile", "#4c78a8"), ("spinup_prepare", "#f58518"),
         ("transfer", "#54a24b"), ("drain_upload", "#b279a2")]
fig, ax = plt.subplots(figsize=(12, 5))
bottom = np.zeros(len(ok))
labels = [f"{r.idx:02d} {r.cc}\n{r.bw}/{r.rtt}/{r.q}" for r in ok.itertuples()]
for name, col in STACK:
    vals = ok[name].astype(float).values
    ax.bar(range(len(ok)), vals, bottom=bottom, label=name, color=col)
    bottom += vals
ax.set_xticks(range(len(ok)))
ax.set_xticklabels(labels, rotation=90, fontsize=7)
ax.set_ylabel("seconds")
ax.set_title("Per-experiment wall-clock decomposition (ATW, 20 runs)")
ax.legend(loc="upper right", ncol=4, fontsize=9)
fig.tight_layout()
fig.savefig(f"{TROOT}/fig_phase_stacked.png", dpi=140)
plt.close(fig)

# ---- 2. median + p10/p90 per phase ----
PHASES = ["healthcheck", "submit_rtt", "compile", "parse", "generate",
          "spinup_prepare", "transfer", "drain_upload",
          "orchestration_overhead", "wall"]
med, p10, p90 = [], [], []
for p in PHASES:
    v = ok[p].astype(float).dropna().values
    med.append(np.median(v)); p10.append(np.percentile(v, 10)); p90.append(np.percentile(v, 90))
med = np.array(med); p10 = np.array(p10); p90 = np.array(p90)
fig, ax = plt.subplots(figsize=(11, 5))
yerr = np.vstack([med - p10, p90 - med])
ax.bar(range(len(PHASES)), med, yerr=yerr, capsize=4, color="#4c78a8", alpha=0.85)
for i, m in enumerate(med):
    ax.text(i, m + max(med) * 0.01, f"{m:.1f}", ha="center", fontsize=8)
ax.set_xticks(range(len(PHASES)))
ax.set_xticklabels(PHASES, rotation=35, ha="right")
ax.set_ylabel("seconds (median, error bars = p10–p90)")
ax.set_title(f"ATW phase timing across {len(ok)} experiments")
# annotate that orchestration_overhead = compile + spinup_prepare + drain_upload
oi = PHASES.index("orchestration_overhead")
ci, si, di = (PHASES.index("compile"), PHASES.index("spinup_prepare"),
              PHASES.index("drain_upload"))
ytop = max(med) * 1.05
ax.annotate("", xy=(ci - 0.4, ytop), xytext=(di + 0.4, ytop),
            arrowprops=dict(arrowstyle="<->", color="crimson", lw=1.2))
ax.text((ci + di) / 2, ytop * 1.02,
        "orchestration_overhead = compile + spin-up + drain  (roll-up, not additive)",
        ha="center", va="bottom", fontsize=8.5, color="crimson")
ax.plot([oi], [med[oi]], marker="o", color="crimson", ms=6, zorder=5)
ax.set_ylim(0, ytop * 1.12)
fig.tight_layout()
fig.savefig(f"{TROOT}/fig_phase_stats.png", dpi=140)
plt.close(fig)

# ---- 3. overhead CDF ----
x = np.sort(ok["orchestration_overhead"].astype(float).values)
y = np.arange(1, len(x) + 1) / len(x)
fig, ax = plt.subplots(figsize=(8.5, 5))
ax.step(x, y, where="post", lw=1.8, color="tab:purple")
ax.scatter(x, y, s=12, color="tab:purple", alpha=0.5, zorder=3)
for q, style in [(0.5, dict(color="crimson", ls="--")), (0.9, dict(color="gray", ls=":"))]:
    v = np.quantile(x, q)
    ax.axvline(v, lw=1.0, **style)
    ax.annotate(f"p{int(q*100)} = {v:.0f}s", xy=(v, q), xytext=(v + 1, q - 0.06),
                fontsize=9, color=style["color"])
ax.set_xlabel("orchestration overhead = wall − transfer (s)")
ax.set_ylabel("CDF (fraction of runs ≤ x)")
ax.set_title("ATW orchestration overhead per experiment")
ax.set_ylim(0, 1.02)
fig.tight_layout()
fig.savefig(f"{TROOT}/fig_overhead_cdf.png", dpi=140)
plt.close(fig)

# ---- 4. tokens ----
tok = pd.read_csv(f"{TROOT}/tokens.csv")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
a1.bar(range(len(tok)), tok["parse_in_tokens"], color="#4c78a8", label="input")
a1.bar(range(len(tok)), tok["parse_out_tokens"], bottom=tok["parse_in_tokens"],
       color="#f58518", label="output")
a1.set_xticks(range(len(tok)))
a1.set_xticklabels(tok["cc"], rotation=90, fontsize=7)
a1.set_ylabel("tokens"); a1.set_title("Intent→config (parse_intent) tokens per experiment")
a1.legend(fontsize=8)
a2.hist(tok["parse_in_tokens"].dropna(), bins=12, color="#4c78a8", alpha=0.85)
a2.set_xlabel("input tokens"); a2.set_ylabel("count")
a2.set_title(f"Input-token distribution (median {int(tok['parse_in_tokens'].median())})")
fig.tight_layout()
fig.savefig(f"{TROOT}/fig_tokens.png", dpi=140)
plt.close(fig)

# ---- 5. queue-occupancy gallery from collected qtraces ----
def load_bottleneck(run_dir):
    qs = glob.glob(f"{run_dir}/queue_trace__*.jsonl")
    if not qs:
        return None
    per = {}
    for line in open(qs[0]):
        try:
            d = json.loads(line)
        except Exception:
            continue
        ifc = d.get("iface"); per.setdefault(ifc, {"t": [], "b": []})
        per[ifc]["t"].append(d.get("t")); per[ifc]["b"].append(d.get("backlog_pkts") or 0)
    best = max(per, key=lambda k: max(per[k]["b"]) if per[k]["b"] else -1)
    t = np.array([x for x in per[best]["t"] if x is not None], float)
    b = np.array(per[best]["b"], float)
    return t - t[0], b


run_dirs = sorted(glob.glob(f"{TROOT}/runs/*/"))
gal = [(d, load_bottleneck(d)) for d in run_dirs]
gal = [(d, r) for d, r in gal if r is not None]
n = len(gal)
if n:
    cols = 4; rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(13, 2.6 * rows), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (d, (tt, bb)) in zip(axes.flat, gal):
        ax.axis("on")
        tag = os.path.basename(d.rstrip("/"))
        parts = tag.split("_")
        cc = parts[-1]
        ax.plot(tt, bb, lw=0.6, color="#4c78a8")
        ax.set_title(tag.replace("_", " "), fontsize=8)
        ax.set_xlim(0, 60)
    fig.suptitle("ATW bottleneck queue occupancy — collected runs", y=1.0, fontsize=13)
    fig.tight_layout()
    fig.savefig(f"{TROOT}/fig_queue_gallery.png", dpi=130)
    plt.close(fig)
    print(f"wrote gallery with {n} traces")

print("analyze.py done — figures in", TROOT)
