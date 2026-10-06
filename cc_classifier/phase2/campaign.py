#!/usr/bin/env python3
"""Full CCAnalyzer collection campaign — resumable, terminal-only (mahimahi).

Collects the self-consistent mahimahi dataset the paper needs, ALL reps:
  * TRAINING (iperf, 20 s):   15 CCA x 9 settings x 3 reps = 405
  * TESTING  (wget, 60 s):    15 CCA x 9 settings x 5 reps = 675
  * EXP11    (wget, 60 s):    15 CCA x 7 queues @0.3bw-275rtt x 2 reps = 210
Total 1290 cells. Sequential (iperf sets the global sysctl CCA — no parallelism).
Resumable: completed cell ids are appended to done.txt; a restart skips them.

No root: mahimahi is setuid, CCA via the granted scoped-sudo sysctl / cc_server.
"""
import os, csv, subprocess, time, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CELLS = os.path.join(HERE, "cells.csv")
DONE = os.path.join(HERE, "done.txt")
IPERF = os.path.join(HERE, "run_iperf_cell.sh")
WGET = os.path.join(HERE, "run_wget_cell.sh")

CCAS = ["reno", "cubic", "bbr", "bic", "cdg", "highspeed", "htcp", "hybla",
        "illinois", "nv", "scalable", "vegas", "veno", "westwood", "yeah"]
SETTINGS = [(5, 85, 64), (5, 130, 64), (5, 275, 128),
            (10, 85, 128), (10, 130, 128), (10, 275, 256),
            (15, 85, 256), (15, 130, 256), (15, 275, 512)]
EXP11_Q = [8, 16, 32, 64, 128, 256, 512]


def build_manifest():
    rows, cid = [], 0
    for (bw, rtt, q) in SETTINGS:            # training
        for cca in CCAS:
            for rep in range(3):
                rows.append([cid, "training", bw, rtt, q, cca, rep, 20]); cid += 1
    for (bw, rtt, q) in SETTINGS:            # testing
        for cca in CCAS:
            for rep in range(5):
                rows.append([cid, "testing", bw, rtt, q, cca, rep, 60]); cid += 1
    for q in EXP11_Q:                        # exp11 low-bw sweep
        for cca in CCAS:
            for rep in range(2):
                rows.append([cid, "exp11", 0.3, 275, q, cca, rep, 60]); cid += 1
    with open(CELLS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "role", "bw", "rtt", "queue", "cca", "rep", "secs"])
        w.writerows(rows)
    return rows


def main():
    if not os.path.exists(CELLS):
        rows = build_manifest()
    else:
        with open(CELLS) as f:
            rows = [list(r.values()) for r in csv.DictReader(f)]
            rows = [[int(r[0]), r[1], r[2], r[3], r[4], r[5], int(r[6]), int(r[7])]
                    for r in rows]
    done = set()
    if os.path.exists(DONE):
        done = {int(x) for x in open(DONE).read().split() if x.strip()}

    total = len(rows)
    todo = [r for r in rows if r[0] not in done]
    print(f"[campaign] {total} cells total, {len(done)} done, {len(todo)} to run", flush=True)
    t_start = time.time()

    for i, (cid, role, bw, rtt, q, cca, rep, secs) in enumerate(todo):
        port = 5600 + (cid % 350)
        script = IPERF if role == "training" else WGET
        out = None if role == "training" else \
            (os.path.join(HERE, "test") if role == "testing"
             else os.path.join(HERE, "exp11"))
        args = ["bash", script, str(bw), str(rtt), str(q), cca, str(rep),
                str(secs), str(port)]
        if out:
            args.append(out)
        try:
            r = subprocess.run(args, capture_output=True, text=True,
                               timeout=secs + 90)
            ok = r.returncode == 0 and "occ_rows=0 " not in r.stdout
            line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"
        except Exception as e:
            ok, line = False, f"EXC {e}"
        if ok:
            with open(DONE, "a") as f:
                f.write(f"{cid}\n")
        el = time.time() - t_start
        rate = (i + 1) / el if el else 0
        eta_h = (len(todo) - i - 1) / rate / 3600 if rate else 0
        print(f"[{i+1}/{len(todo)}] id={cid} {role} {'OK ' if ok else 'FAIL'} "
              f"| {line} | ETA {eta_h:.1f}h", flush=True)

    print(f"[campaign] finished in {(time.time()-t_start)/3600:.1f}h", flush=True)


if __name__ == "__main__":
    main()
