#!/usr/bin/env python3
"""Phase-1 analysis — terminal-only re-analysis of the already-collected 183
queue-occupancy traces. Produces the data behind paper Fig 7 / 10 / 14 / 17.
Caches everything to phase1_data.json so the notebook just plots (fast, re-runnable).

No ATW, no new collection. 1NN-DTW is the same method proven at 90% within-setting.
Protocol here is cross-setting leave-one-setting-out (1 rep/cell, so within-setting is
impossible over cc_results alone) — a harder generalization view that still yields the
per-setting grid, truncation curve, and per-CCA votes the figures need.
"""
import os, sys, json, glob, csv
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CC = os.path.dirname(HERE)
sys.path.insert(0, CC)
from run_classifier import load_trace, resample_window, dtw_batch, find_data_dir, FNAME_RE

N = 110
BANDS = None  # use run_classifier default
ACCURATE = ["10bw-130rtt-128q", "10bw-85rtt-128q", "5bw-130rtt-64q", "5bw-85rtt-64q"]
TRUNC_LENGTHS = [10, 20, 30, 40, 50, 60]
OUT = os.path.join(HERE, "phase1_data.json")


def load_all():
    d = find_data_dir()
    files = sorted(glob.glob(os.path.join(d, "*qtrace.jsonl")))
    recs = []
    for f in files:
        m = FNAME_RE.match(os.path.basename(f))
        if not m:
            continue
        cca = m.group(1)
        qcap = float(m.group(4))
        setting = f"{m.group(2)}bw-{m.group(3)}rtt-{m.group(4)}q"
        tr = load_trace(f)
        if tr is None:
            continue
        t, y = tr
        # per-trace bytes = last cumulative bytes_sent on the bottleneck
        bytes_total = _bytes_of(f)
        recs.append(dict(cca=cca, setting=setting, qcap=qcap,
                         t=t, y=y, bytes=bytes_total))
    return recs, d


def _bytes_of(path):
    last = 0
    for line in open(path):
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("iface") == "veth2" and o.get("bytes_sent"):
            last = o["bytes_sent"]
    return last


def loo_predict(X, ccas, settings):
    """cross-setting leave-one-setting-out 1NN-DTW over resampled matrix X."""
    M = len(ccas)
    D = np.zeros((M, M))
    for i in range(M):
        D[i] = dtw_batch(X[i], X)
    np.fill_diagonal(D, np.inf)
    preds = np.empty(M, dtype=object)
    for i in range(M):
        cand = np.where(settings != settings[i])[0]
        preds[i] = ccas[cand[np.argmin(D[i, cand])]]
    return preds


def main():
    recs, ddir = load_all()
    ccas = np.array([r["cca"] for r in recs])
    settings = np.array([r["setting"] for r in recs])
    print(f"loaded {len(recs)} traces from {ddir}")

    # --- Fig 7 + Fig 14: full-window LOO at 20 s ---
    X20 = np.stack([resample_window(r["t"], r["y"], 20.0, N) for r in recs])
    preds = loo_predict(X20, ccas, settings)
    correct = preds == ccas

    labels = sorted(set(ccas))
    settings_sorted = sorted(set(settings))

    # per-setting accuracy (Fig 7 row summary)
    per_setting_acc = {s: float(correct[settings == s].mean()) for s in settings_sorted}
    # confusion matrix (Fig 7 grid)
    li = {c: k for k, c in enumerate(labels)}
    conf = np.zeros((len(labels), len(labels)), int)
    for tr, pr in zip(ccas, preds):
        conf[li[tr], li[pr]] += 1
    # per-CCA vote across settings (Fig 14)
    votes = {}
    for c in labels:
        idx = np.where(ccas == c)[0]
        v = list(preds[idx])
        win = max(set(v), key=v.count)
        votes[c] = dict(winner=win, correct=bool(win == c),
                        agree=v.count(win), n=len(v))
    vote_acc = sum(1 for x in votes.values() if x["correct"]) / len(votes)
    print(f"Fig7 per-trace {correct.mean()*100:.1f}% | Fig14 vote {vote_acc*100:.1f}%")

    # --- Fig 10: truncation sweep ---
    trunc = {}
    for L in TRUNC_LENGTHS:
        XL = np.stack([resample_window(r["t"], r["y"], float(L), N) for r in recs])
        p = loo_predict(XL, ccas, settings)
        trunc[L] = float((p == ccas).mean())
        print(f"  trunc {L}s: {trunc[L]*100:.1f}%")

    # --- Fig 17: efficiency (bytes + time per CCA over the 4 accurate settings) ---
    times = {}
    et = os.path.join(CC, "..", "cc_results", "execution_time_table.csv")
    if os.path.exists(et):
        for row in csv.DictReader(open(et)):
            key = (row["cc"], f'{row["bw_mbps"]}bw-{row["rtt_ms"]}rtt-{row["queue_pkts"]}q')
            try:
                times[key] = float(row["exec_time_submit_to_data_s"])
            except Exception:
                pass
    eff = {}
    for c in labels:
        b = t = 0.0
        n = 0
        for r in recs:
            if r["cca"] == c and r["setting"] in ACCURATE:
                b += r["bytes"]
                t += times.get((c, r["setting"]), 60.0)
                n += 1
        eff[c] = dict(bytes_mb=b / 1e6, time_s=t, n_traces=n)

    data = dict(
        labels=labels, settings=settings_sorted,
        per_trace_acc=float(correct.mean()), vote_acc=vote_acc,
        per_setting_acc=per_setting_acc,
        confusion=conf.tolist(),
        votes=votes,
        truncation={str(k): v for k, v in trunc.items()},
        efficiency=eff,
        n_traces=len(recs),
    )
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
