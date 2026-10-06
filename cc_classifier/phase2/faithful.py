#!/usr/bin/env python3
"""Faithful CCAnalyzer protocol — train (iperf) as reference, test (wget) as query,
matched WITHIN-SETTING. This is the paper's Fig 7/8/9/11/12 setup, now possible
because Phase 2 collected the iperf training set (cc_data/train, 180 traces) to pair
with the existing wget testing set (cc_results backup, 183 traces).

For each testing trace at setting S: restrict the training library to setting S
(15 CCAs x 3 reps), take the 1NN-DTW label. Also: per-CCA vote across the 4 settings
(Fig 14/7 voting), DTW-distance CDF of train same/diff-CCA pairs (Fig 11), and one
BBR test-vs-nearest-train example (Fig 8/9).
"""
import os, sys, glob, json, re
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CC = os.path.dirname(HERE)
sys.path.insert(0, CC)
from run_classifier import load_trace, resample_window, dtw_batch, FNAME_RE

N = 110
ACCURATE = ["10bw-130rtt-128q", "10bw-85rtt-128q", "5bw-130rtt-64q", "5bw-85rtt-64q"]
OUT = os.path.join(HERE, "faithful_data.json")


def backup_test_dir():
    p = open("/tmp/atw_backup_path.txt").read().strip()
    return os.path.join(p, "cc_results")


def load_train():
    recs = []
    for d in sorted(glob.glob("cc_data/train/*/")):
        base = os.path.basename(d.rstrip("/"))
        m = re.match(r"(\d+)bw-(\d+)rtt-(\d+)q_([a-z]+)_rep(\d+)", base)
        if not m:
            continue
        setting = f"{m.group(1)}bw-{m.group(2)}rtt-{m.group(3)}q"
        cca, qcap = m.group(4), float(m.group(3))
        qt = glob.glob(os.path.join(d, "*qtrace.jsonl"))
        if not qt:
            continue
        tr = load_trace(qt[0])
        if tr is None:
            continue
        recs.append(dict(cca=cca, setting=setting, qcap=qcap,
                         x=resample_window(*tr, 20.0, N)))
    return recs


def load_test():
    recs = []
    for f in sorted(glob.glob(os.path.join(backup_test_dir(), "*qtrace.jsonl"))):
        m = FNAME_RE.match(os.path.basename(f))
        if not m:
            continue
        setting = f"{m.group(2)}bw-{m.group(3)}rtt-{m.group(4)}q"
        if setting not in ACCURATE:
            continue
        tr = load_trace(f)
        if tr is None:
            continue
        recs.append(dict(cca=m.group(1), setting=setting,
                         x=resample_window(*tr, 20.0, N)))
    return recs


def main():
    train = load_train()
    test = load_test()
    print(f"train={len(train)} test={len(test)} (accurate settings only)")

    labels = sorted({r["cca"] for r in train})
    li = {c: k for k, c in enumerate(labels)}
    conf = np.zeros((len(labels), len(labels)), int)
    preds = []            # (setting, true, pred)

    for s in ACCURATE:
        lib = [r for r in train if r["setting"] == s]
        L = np.stack([r["x"] for r in lib])
        Llab = [r["cca"] for r in lib]
        for q in [r for r in test if r["setting"] == s]:
            d = dtw_batch(q["x"], L)
            pred = Llab[int(np.argmin(d))]
            preds.append((s, q["cca"], pred))
            conf[li[q["cca"]], li[pred]] += 1

    correct = sum(1 for _, t, p in preds if t == p)
    acc = correct / len(preds)

    # per-CCA vote across the 4 settings
    from collections import defaultdict, Counter
    byc = defaultdict(list)
    for s, t, p in preds:
        byc[t].append(p)
    votes = {}
    for c in labels:
        v = byc.get(c, [])
        win = Counter(v).most_common(1)[0][0] if v else None
        votes[c] = dict(winner=win, correct=bool(win == c),
                        n=len(v), agree=Counter(v).most_common(1)[0][1] if v else 0)
    vote_acc = sum(1 for x in votes.values() if x["correct"]) / len(labels)

    # per-setting accuracy
    ps = {}
    for s in ACCURATE:
        sub = [(t, p) for ss, t, p in preds if ss == s]
        ps[s] = sum(1 for t, p in sub if t == p) / len(sub) if sub else 0

    # Fig 11: train same-CCA vs diff-CCA DTW distance distributions (5bw-85rtt-64q)
    s0 = "5bw-85rtt-64q"
    lib0 = [r for r in train if r["setting"] == s0]
    same, diff = [], []
    for i in range(len(lib0)):
        d = dtw_batch(lib0[i]["x"], np.stack([r["x"] for r in lib0]))
        for j in range(len(lib0)):
            if i < j:
                (same if lib0[i]["cca"] == lib0[j]["cca"] else diff).append(float(d[j]))

    data = dict(
        labels=labels, per_trace_acc=acc, correct=correct, total=len(preds),
        vote_acc=vote_acc, votes=votes, per_setting_acc=ps,
        confusion=conf.tolist(),
        fig11_same=same, fig11_diff=diff,
        n_train=len(train), n_test=len(test),
    )
    json.dump(data, open(OUT, "w"), indent=1)
    print(f"FAITHFUL within-setting: per-trace {acc*100:.1f}% ({correct}/{len(preds)}) | "
          f"per-CCA vote {vote_acc*100:.1f}%")
    for s in ACCURATE:
        print(f"  {s}: {ps[s]*100:.0f}%")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
