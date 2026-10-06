#!/usr/bin/env python3
"""
Within-setting 1NN-DTW, cross-collection — the paper's actual protocol.

Reference library : the 183 cc_results traces (from the backup), indexed by setting.
Test set          : the 20 atw_cc_timing traces (a separate campaign).
Match             : for a test trace at setting S, restrict the reference library to
                    setting S (all 15 CCAs, one each) and take the DTW-nearest CCA.

Because reference and test come from *different* campaigns, a correct match means the
same-CCA/same-setting queue-occupancy shape is stable run-to-run — i.e. it tests whether
we reproduce the paper's high within-setting accuracy (Fig 7 ~96%).
"""

import glob, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_classifier import (
    load_trace,
    resample_window,
    dtw_batch,
    find_data_dir,
    FNAME_RE,
)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
TIMING_DIR = os.path.join(os.path.dirname(OUT_DIR), "atw_cc_timing", "runs")
DIRNAME_RE = re.compile(r"^\d+_(\d+bw-\d+rtt-(\d+)q)_([a-z0-9]+)$")


def load_reference():
    ref_dir = find_data_dir()
    ref = {}  # setting -> list of (cca, raw, norm)
    for f in sorted(glob.glob(os.path.join(ref_dir, "*qtrace.jsonl"))):
        m = FNAME_RE.match(os.path.basename(f))
        if not m:
            continue
        cca = m.group(1)
        qcap = float(m.group(4))
        setting = f"{m.group(2)}bw-{m.group(3)}rtt-{m.group(4)}q"
        tr = load_trace(f)
        if tr is None:
            continue
        yr = resample_window(*tr)
        ref.setdefault(setting, []).append(
            (cca, yr.astype(float), (yr / qcap).astype(float))
        )
    return ref, ref_dir


def load_tests():
    tests = []  # (cca, setting, qcap, raw, norm)
    for d in sorted(glob.glob(os.path.join(TIMING_DIR, "*"))):
        m = DIRNAME_RE.match(os.path.basename(d))
        if not m:
            continue
        setting, qcap, cca = m.group(1), float(m.group(2)), m.group(3)
        qf = glob.glob(os.path.join(d, "*qtrace.jsonl"))
        if not qf:
            continue
        tr = load_trace(qf[0])
        if tr is None:
            continue
        yr = resample_window(*tr)
        tests.append((cca, setting, qcap, yr.astype(float), (yr / qcap).astype(float)))
    return tests


def classify(tests, ref, variant):
    idx = 1 if variant == "raw" else 2  # tuple position of the series
    rows, correct = [], 0
    for cca, setting, qcap, raw, norm in tests:
        q = raw if variant == "raw" else norm
        lib = ref.get(setting, [])
        labels = [e[0] for e in lib]
        B = np.stack([e[idx] for e in lib])
        d = dtw_batch(q, B)
        k = int(np.argmin(d))
        pred = labels[k]
        # rank of the true CCA (how close the correct reference was)
        order = np.argsort(d)
        true_positions = [labels[o] for o in order]
        rank = true_positions.index(cca) + 1 if cca in true_positions else None
        ok = pred == cca
        correct += ok
        rows.append((setting, cca, pred, ok, rank))
    return rows, correct


def main():
    ref, ref_dir = load_reference()
    tests = load_tests()
    print(
        f"reference: {sum(len(v) for v in ref.values())} traces / "
        f"{len(ref)} settings  (from {ref_dir})"
    )
    print(f"test:      {len(tests)} timing traces\n")

    for variant in ("raw", "norm"):
        rows, correct = classify(tests, ref, variant)
        acc = correct / len(rows)
        print(f"=== within-setting, variant={variant} ===")
        print(f"{'setting':18s} {'true':10s} {'pred':10s} {'ok':3s} rank")
        for setting, cca, pred, ok, rank in rows:
            print(
                f"{setting:18s} {cca:10s} {pred:10s} " f"{'Y' if ok else '.':3s} {rank}"
            )
        print(f"accuracy: {correct}/{len(rows)} = {acc*100:.1f}%\n")


if __name__ == "__main__":
    main()
