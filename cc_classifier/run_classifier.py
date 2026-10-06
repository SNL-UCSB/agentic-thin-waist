#!/usr/bin/env python3
"""
1NN-DTW CCA classifier over the ATW-collected queue-occupancy traces.

Faithful-as-possible reproduction of CCAnalyzer's Exp6 classifier given our data:
  * Data = 183 wget queue-occupancy traces (bottleneck veth2 backlog_pkts), 15 CCAs.
  * We have ONE rep per (cca, setting) cell, so the paper's within-setting
    (3 train / 5 test reps) split is impossible. We therefore run
    LEAVE-ONE-SETTING-OUT cross-validation: train on all other settings, test on
    the held-out setting. Train/test are disjoint (different network conditions),
    so no trace is ever its own nearest neighbor.
  * Classifier = 1-Nearest-Neighbor with banded (Sakoe-Chiba) DTW, matching the
    paper's 1NN-DTW over bottleneck queue occupancy.
  * Preprocess = first 20 s (paper: ~20 s suffices), resampled to N points.
    Two amplitude variants: RAW (packets) and NORM (occupancy / queue capacity).

Outputs a JSON + text summary; plots a confusion matrix if matplotlib is present.
"""

import json, os, re, sys, glob, math
import numpy as np

# ---- config ----
DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else None
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW_S = 20.0  # paper: ~20 s of the trace is enough
N = 128  # resample length for DTW
BAND = 16  # Sakoe-Chiba band radius
BOTTLENECK_IFACE = "veth2"

FNAME_RE = re.compile(r"^([a-z0-9]+)_(\d+)bw-(\d+)rtt-(\d+)q__")


def find_data_dir():
    if DATA_DIR and os.path.isdir(DATA_DIR):
        return DATA_DIR
    # look for a backup dir holding cc_results qtraces
    for base in glob.glob("/home/jaber/atw_data_backup_*/cc_results"):
        if glob.glob(os.path.join(base, "*qtrace.jsonl")):
            return base
    raise SystemExit("Could not locate cc_results qtraces; pass the dir as argv[1].")


def load_trace(path):
    """Return (t_rel, backlog_pkts) for the bottleneck iface, sorted by time."""
    ts, ys = [], []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            o = json.loads(line)
            if o.get("iface") != BOTTLENECK_IFACE:
                continue
            v = o["backlog_pkts"]
            if v is None:  # transient tc read gap -> skip, interp bridges it
                continue
            ts.append(o["t"])
            ys.append(v)
    if not ts:
        return None
    t = np.asarray(ts, float)
    y = np.asarray(ys, float)
    order = np.argsort(t)
    t, y = t[order], y[order]
    t -= t[0]
    return t, y


def resample_window(t, y, window_s=WINDOW_S, n=N):
    """Uniformly resample the first `window_s` seconds to n points."""
    grid = np.linspace(0.0, window_s, n)
    # np.interp holds last value past the end; fine (traces span ~60 s > 20 s)
    return np.interp(grid, t, y)


def dtw_batch(q, B, band=BAND):
    """Sakoe-Chiba banded DTW from one query q (len n) to every row of B (m x n),
    vectorized over the m targets. Returns array of m distances."""
    n = len(q)
    m = B.shape[0]
    INF = 1e18
    prev = np.full((m, n + 1), INF)
    prev[:, 0] = 0.0
    for i in range(1, n + 1):
        cur = np.full((m, n + 1), INF)
        jlo = max(1, i - band)
        jhi = min(n, i + band)
        qi = q[i - 1]
        for j in range(jlo, jhi + 1):
            d = (qi - B[:, j - 1]) ** 2
            best = np.minimum(prev[:, j], prev[:, j - 1])
            best = np.minimum(best, cur[:, j - 1])
            cur[:, j] = d + best
        prev = cur
    return np.sqrt(prev[:, n])


def main():
    data_dir = find_data_dir()
    files = sorted(glob.glob(os.path.join(data_dir, "*qtrace.jsonl")))
    print(f"data dir: {data_dir}")
    print(f"traces:   {len(files)}")

    ccas, settings, raw, norm = [], [], [], []
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
        yr = resample_window(t, y)
        ccas.append(cca)
        settings.append(setting)
        raw.append(yr.astype(float))
        norm.append((yr / qcap).astype(float))

    ccas = np.array(ccas)
    settings = np.array(settings)
    M = len(ccas)
    print(f"loaded:   {M} traces, {len(set(ccas))} CCAs, {len(set(settings))} settings")

    results = {}
    for variant, series in (("raw", raw), ("norm", norm)):
        X = np.stack(series)
        # full pairwise DTW, one batched pass per query row
        D = np.zeros((M, M))
        for i in range(M):
            D[i] = dtw_batch(X[i], X)
        np.fill_diagonal(D, np.inf)  # never pick self
        # leave-one-setting-out 1NN
        preds = np.empty(M, dtype=object)
        for i in range(M):
            mask = settings != settings[i]  # train = other settings only
            cand = np.where(mask)[0]
            nn = cand[np.argmin(D[i, cand])]
            preds[i] = ccas[nn]
        correct = preds == ccas
        acc = correct.mean()

        # per-setting accuracy (only the 12 full 15-CCA settings are meaningful)
        per_setting = {}
        for s in sorted(set(settings)):
            idx = settings == s
            per_setting[s] = (int(correct[idx].sum()), int(idx.sum()))

        # per-CCA recall
        per_cca = {}
        for c in sorted(set(ccas)):
            idx = ccas == c
            per_cca[c] = (int(correct[idx].sum()), int(idx.sum()))

        # voting: majority vote of a CCA's per-setting predictions -> 1 label / CCA
        voted = {}
        for c in sorted(set(ccas)):
            idx = np.where(ccas == c)[0]
            votes = list(preds[idx])
            win = max(set(votes), key=votes.count)
            voted[c] = (win, win == c, votes.count(win), len(votes))
        vote_acc = sum(1 for v in voted.values() if v[1]) / len(voted)

        # voting restricted to the paper's 4 "most accurate" settings
        ACCURATE = {
            "10bw-130rtt-128q",
            "10bw-85rtt-128q",
            "5bw-130rtt-64q",
            "5bw-85rtt-64q",
        }
        voted4 = {}
        for c in sorted(set(ccas)):
            idx = np.where((ccas == c) & np.isin(settings, list(ACCURATE)))[0]
            if len(idx) == 0:
                continue
            votes = list(preds[idx])
            win = max(set(votes), key=votes.count)
            voted4[c] = (win, win == c, votes.count(win), len(votes))
        vote4_acc = (
            sum(1 for v in voted4.values() if v[1]) / len(voted4) if voted4 else 0.0
        )

        # confusion counts (true -> predicted), for wrong predictions
        confl = {}
        for t_, p_ in zip(ccas, preds):
            if t_ != p_:
                confl[(t_, p_)] = confl.get((t_, p_), 0) + 1

        results[variant] = dict(
            per_trace_acc=acc,
            per_trace_correct=int(correct.sum()),
            per_trace_total=int(M),
            vote_acc=vote_acc,
            vote4_acc=vote4_acc,
            per_setting=per_setting,
            per_cca=per_cca,
            voted=voted,
            voted4=voted4,
            preds=list(preds),
            truth=list(ccas),
            settings=list(settings),
        )
        print(f"\n=== variant={variant} ===")
        print(f"per-trace           : {int(correct.sum())}/{M} = {acc*100:.1f}%")
        print(
            f"per-CCA vote (all 12): {sum(1 for v in voted.values() if v[1])}/{len(voted)} "
            f"= {vote_acc*100:.1f}%"
        )
        print(
            f"per-CCA vote (4 acc): {sum(1 for v in voted4.values() if v[1])}/{len(voted4)} "
            f"= {vote4_acc*100:.1f}%"
        )
        print("per-CCA recall:")
        for c in sorted(per_cca):
            n_ok, n_tot = per_cca[c]
            print(f"   {c:10s} {n_ok:2d}/{n_tot:2d}")
        top = sorted(confl.items(), key=lambda kv: -kv[1])[:8]
        print(
            "top confusions (true->pred): "
            + ", ".join(f"{a}->{b}:{n}" for (a, b), n in top)
        )

    with open(os.path.join(OUT_DIR, "classifier_results.json"), "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nwrote {os.path.join(OUT_DIR, 'classifier_results.json')}")

    # confusion-matrix figure (norm variant)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = sorted(set(ccas))
        li = {c: k for k, c in enumerate(labels)}
        for variant in ("raw", "norm"):
            r = results[variant]
            C = np.zeros((len(labels), len(labels)), int)
            for t_, p_ in zip(r["truth"], r["preds"]):
                C[li[t_], li[p_]] += 1
            fig, ax = plt.subplots(figsize=(8, 7))
            im = ax.imshow(C, cmap="Blues")
            ax.set_xticks(range(len(labels)))
            ax.set_yticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=90, fontsize=8)
            ax.set_yticklabels(labels, fontsize=8)
            ax.set_xlabel("predicted CCA")
            ax.set_ylabel("true CCA")
            ax.set_title(
                f"1NN-DTW leave-one-setting-out ({variant})  "
                f"per-trace {r['per_trace_acc']*100:.1f}%  "
                f"vote {r['vote_acc']*100:.0f}%"
            )
            for i in range(len(labels)):
                for j in range(len(labels)):
                    if C[i, j]:
                        ax.text(
                            j,
                            i,
                            C[i, j],
                            ha="center",
                            va="center",
                            fontsize=7,
                            color="white" if C[i, j] > C.max() / 2 else "black",
                        )
            fig.colorbar(im, fraction=0.046)
            fig.tight_layout()
            p = os.path.join(OUT_DIR, f"confusion_{variant}.png")
            fig.savefig(p, dpi=130)
            plt.close(fig)
            print(f"wrote {p}")
    except Exception as e:
        print(f"(no confusion figure: {e})")
    return results


if __name__ == "__main__":
    main()
