#!/usr/bin/env python3
"""Aggregate per-run phases.env files into phase-resolved timing + token tables.

Phases (seconds), derived from the epoch marks each run recorded:
  healthcheck        = t_health_done   - t_health_start
  submit_rtt         = t_submit_done   - t_submit
  compile            = t_status_executing - t_status_parsing      (intent->spec)
    . parse          = t_status_generating - t_status_parsing     (parse_intent LLM)
    . generate       = t_status_executing  - t_status_generating  (spec/param prep)
  spinup_prepare     = t_transfer_start - t_status_executing      (Docker container
                        spin-up + shaping + workflow dispatch; ephemeral so not
                        separately observable on :8002)
  transfer           = t_transfer_end   - t_transfer_start        (data-gen ~60 s)
  drain_upload       = t_status_complete - t_transfer_end         (capture drain +
                        pcap/qtrace upload to telemetry + status flip)
  orchestration_overhead = wall - transfer
                     = compile + spinup_prepare + drain_upload (+ ~0.2 s submit/poll
                       slack). This is a ROLL-UP of the three non-transfer work phases,
                       NOT a separate segment — do not add it on top of them.
  wall               = t_status_complete - t_submit
                     = orchestration_overhead + transfer
Writes timing.csv (one row/run + a stats block) and tokens.csv, prints a summary.
"""
import csv
import glob
import os
import statistics as st

TROOT = "/home/jaber/agentic-thin-waist/atw_cc_timing"
RUNS = sorted(glob.glob(f"{TROOT}/runs/*/phases.env"))


def load(path):
    d = {}
    for line in open(path):
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def f(d, k):
    try:
        return float(d[k])
    except (KeyError, ValueError):
        return None


def sub(a, b):
    return round(a - b, 3) if (a is not None and b is not None) else None


PHASE_COLS = [
    "healthcheck", "submit_rtt", "compile", "parse", "generate",
    "spinup_prepare", "transfer", "drain_upload", "orchestration_overhead", "wall",
]

rows = []
for p in RUNS:
    d = load(p)
    r = {
        "tag": d.get("tag"), "idx": d.get("idx"), "bw": d.get("bw"),
        "rtt": d.get("rtt"), "q": d.get("q"), "cc": d.get("cc"),
        "final_status": d.get("final_status", ""),
        "experiment_id": d.get("experiment_id", ""),
        "cc_verified": d.get("cc_verified", ""),
        "backlog_max": d.get("backlog_max", ""),
        "orch_id": d.get("orch_id", ""),
    }
    hs, hd = f(d, "t_health_start"), f(d, "t_health_done")
    ts, td = f(d, "t_submit"), f(d, "t_submit_done")
    tp = f(d, "t_status_parsing")
    tg = f(d, "t_status_generating")
    te = f(d, "t_status_executing")
    tc = f(d, "t_status_complete")
    tfs, tfe = f(d, "t_transfer_start"), f(d, "t_transfer_end")
    r["healthcheck"] = sub(hd, hs)
    r["submit_rtt"] = sub(td, ts)
    r["compile"] = sub(te, tp)
    r["parse"] = sub(tg, tp)
    r["generate"] = sub(te, tg)
    r["spinup_prepare"] = sub(tfs, te)
    r["transfer"] = sub(tfe, tfs)
    r["drain_upload"] = sub(tc, tfe)
    r["wall"] = sub(tc, ts)
    r["orchestration_overhead"] = (
        round(r["wall"] - r["transfer"], 3)
        if (r["wall"] is not None and r["transfer"] is not None) else None
    )
    r["parse_in_tokens"] = d.get("parse_in_tokens", "")
    r["parse_out_tokens"] = d.get("parse_out_tokens", "")
    rows.append(r)

# ---- timing.csv ----
cols = (["tag", "idx", "bw", "rtt", "q", "cc", "cc_verified", "final_status",
         "experiment_id", "backlog_max"] + PHASE_COLS
        + ["parse_in_tokens", "parse_out_tokens", "orch_id"])
with open(f"{TROOT}/timing.csv", "w", newline="") as o:
    w = csv.DictWriter(o, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in cols})


def pct(vals, q):
    vals = sorted(vals)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = q * (len(vals) - 1)
    lo = int(idx)
    frac = idx - lo
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] * (1 - frac) + vals[hi] * frac


ok = [r for r in rows if r["final_status"] == "complete"]
print(f"\n=== PHASE-RESOLVED TIMING (n={len(ok)} completed / {len(rows)} attempted) ===")
print(f"{'phase':<24}{'median':>9}{'p10':>9}{'p90':>9}{'min':>9}{'max':>9}")
stats = {}
for c in PHASE_COLS:
    vals = [r[c] for r in ok if r.get(c) is not None]
    if not vals:
        continue
    med = round(st.median(vals), 2)
    p10 = round(pct(vals, 0.10), 2)
    p90 = round(pct(vals, 0.90), 2)
    stats[c] = (med, p10, p90, round(min(vals), 2), round(max(vals), 2))
    print(f"{c:<24}{med:>9}{p10:>9}{p90:>9}{round(min(vals),2):>9}{round(max(vals),2):>9}")

# append stats block to timing.csv
with open(f"{TROOT}/timing.csv", "a", newline="") as o:
    o.write("\n# NOTE: orchestration_overhead = compile + spinup_prepare + drain_upload\n")
    o.write("#       (a roll-up of the non-transfer phases; wall = orchestration_overhead + transfer).\n")
    o.write("#       Do NOT add orchestration_overhead on top of its components.\n")
    o.write("# phase,median,p10,p90,min,max (seconds; completed runs only)\n")
    for c, (med, p10, p90, mn, mx) in stats.items():
        o.write(f"# {c},{med},{p10},{p90},{mn},{mx}\n")

# ---- tokens.csv ----
with open(f"{TROOT}/tokens.csv", "w", newline="") as o:
    w = csv.writer(o)
    w.writerow(["tag", "cc", "bw", "rtt", "q", "parse_in_tokens", "parse_out_tokens",
                "parse_total_tokens"])
    for r in rows:
        ti = r.get("parse_in_tokens") or ""
        to = r.get("parse_out_tokens") or ""
        tot = ""
        try:
            tot = int(ti) + int(to)
        except ValueError:
            pass
        w.writerow([r["tag"], r["cc"], r["bw"], r["rtt"], r["q"], ti, to, tot])

tin = [int(r["parse_in_tokens"]) for r in rows if str(r.get("parse_in_tokens")).isdigit()]
tou = [int(r["parse_out_tokens"]) for r in rows if str(r.get("parse_out_tokens")).isdigit()]
if tin:
    print(f"\n=== INTENT->CONFIG TOKENS (parse_intent, n={len(tin)}) ===")
    print(f"input : median {int(st.median(tin))}  min {min(tin)}  max {max(tin)}")
    print(f"output: median {int(st.median(tou))}  min {min(tou)}  max {max(tou)}")
    print(f"total : median {int(st.median(tin))+int(st.median(tou))} tokens / conversion")
print("\nwrote timing.csv and tokens.csv")
