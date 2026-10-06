#!/usr/bin/env python3
"""Resumable ATW-driven collection campaign (per cc.md).

All shaping (bw/latency/queue) goes through Agentic Thin Waist: POST /intent with a
deterministic `context`, host sender-CC via scoped sudo sysctl, artifacts pulled from
the telemetry service. Reuses the proven flow in atw_cc_timing/harness/run_one.sh.

Roles:
  wget_test  -> test_wget_workflow  (works today)               -> cc_data/test/
  iperf_train-> test_iperf3_workflow (needs service restart)    -> cc_data/train/
  exp11      -> test_wget_workflow  @ 0.3 Mbps                   -> cc_data/exp11/
Resumable: completed tags are appended to done.txt; a restart skips them.
"""

import os, sys, json, time, subprocess, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "cc_data")
DONE = os.path.join(HERE, "atw_done.txt")
ORCH = "http://localhost:8005"
TELE = "http://localhost:8004"
ORIGIN = "http://128.111.5.237:8888/1GB.bin"
IPERF_HOST, IPERF_PORT = "128.111.5.237", 5399

CCAS = [
    "reno",
    "cubic",
    "bbr",
    "bic",
    "cdg",
    "highspeed",
    "htcp",
    "hybla",
    "illinois",
    "nv",
    "scalable",
    "vegas",
    "veno",
    "westwood",
    "yeah",
]
SETTINGS = [
    (5, 85, 64),
    (5, 130, 64),
    (5, 275, 128),
    (10, 85, 128),
    (10, 130, 128),
    (10, 275, 256),
    (15, 85, 256),
    (15, 130, 256),
    (15, 275, 512),
]
# the paper's 4 "most accurate" settings (used for voting) — the trimmed core
ACCURATE = [(10, 130, 128), (10, 85, 128), (5, 130, 64), (5, 85, 64)]
EXP11_Q = [8, 16, 32, 64, 128, 256, 512]

ROLE = sys.argv[1] if len(sys.argv) > 1 else "wget_test"  # which set to collect


def GET(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def POST(url, body, timeout=15):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": str(e)}


def set_cc(cca):
    subprocess.run(
        ["sudo", "-n", "sysctl", "-w", f"net.ipv4.tcp_congestion_control={cca}"],
        capture_output=True,
    )
    got = subprocess.run(
        ["sysctl", "-n", "net.ipv4.tcp_congestion_control"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return got == cca


def intent_body(role, bw, rtt, q, cca, dur):
    ctx = {
        "capacities": [float(bw)],
        "latencies": [float(rtt)],
        "cc_algorithms": [cca],
        "aqm_policy": "pfifo",
        "buffer_packets": int(q),
        "qdisc_params": {},
        "duration_seconds": int(dur),
        "num_trials": 1,
    }
    if role == "iperf_train":
        intent = (
            f"Run an iperf3 reverse test to {IPERF_HOST}:{IPERF_PORT} for "
            f"{dur} seconds over a {bw} Mbps bottleneck with {rtt} ms added "
            f"latency, pfifo queue of {q} packets and {cca} congestion "
            f"control. One trial."
        )
        wid = "test_iperf3_workflow"
    else:
        intent = (
            f"Run a wget download from {ORIGIN} over a {bw} Mbps bottleneck "
            f"with {rtt} ms added latency, pfifo queue of {q} packets and "
            f"{cca} congestion control. Write it to /dev/null. Stop wget after "
            f"{dur} seconds. One trial."
        )
        wid = "test_wget_workflow"
    return {
        "intent": intent,
        "workflow_source": "library",
        "workflow_id": wid,
        "context": ctx,
    }


def collect(orch_id, outdir):
    res = GET(f"{ORCH}/orchestration/{orch_id}/results") or {}
    rlist = res.get("results") or [{}]
    exp = rlist[0].get("experiment_id", "") if rlist else ""
    if not exp:
        return False, "no experiment_id"
    rid = ""
    for _ in range(30):
        r = GET(f"{TELE}/results?experiment_id={exp}&limit=1") or {}
        rl = r.get("results") or []
        if rl:
            rid = rl[0].get("result_id", "")
        if rid:
            break
        time.sleep(1)
    if not rid:
        return False, "no result_id"
    os.makedirs(outdir, exist_ok=True)
    full = GET(f"{TELE}/results/{rid}")
    json.dump(full, open(os.path.join(outdir, "result.json"), "w"))
    arts = GET(f"{TELE}/results/{rid}/artifacts") or {}
    got = 0
    for a in arts.get("artifacts", []):
        aid, atype, fn = a["artifact_id"], a["artifact_type"], a["filename"]
        try:
            urllib.request.urlretrieve(
                f"{TELE}/artifacts/{aid}", os.path.join(outdir, f"{atype}__{fn}")
            )
            got += 1
        except Exception:
            pass
    return got > 0, f"exp={exp} artifacts={got}"


def run_cell(role, bw, rtt, q, cca, rep, dur):
    tag = f"{bw}bw-{rtt}rtt-{q}q_{cca}_rep{rep}"
    sub = {"wget_test": "test", "iperf_train": "train", "exp11": "exp11"}[role]
    outdir = os.path.join(DATA, sub, tag)
    if not set_cc(cca):
        return False, tag, "cc-set-failed"
    resp = POST(f"{ORCH}/intent", intent_body(role, bw, rtt, q, cca, dur))
    oid = resp.get("orchestration_id", "")
    if not oid:
        return False, tag, f"submit-failed {resp.get('_error','')}"
    term = ""
    for _ in range(900):
        st = (GET(f"{ORCH}/orchestration/{oid}") or {}).get("status", "")
        if st in ("complete", "failed"):
            term = st
            break
        time.sleep(0.5)
    if term != "complete":
        return False, tag, f"orch={term or 'timeout'}"
    ok, msg = collect(oid, outdir)
    return ok, tag, msg


def manifest(role):
    cells = []
    if role == "train_core":
        # TRIMMED 6h scope: training only, 4 accurate settings x 15 CCA x 3 reps
        # = 180 iperf runs (~4.7h). Reuse existing 183 testing traces.
        for bw, rtt, q in ACCURATE:
            for cca in CCAS:
                for rep in range(3):
                    cells.append(("iperf_train", bw, rtt, q, cca, rep, 20))
    elif role in ("wget_test", "iperf_train"):
        dur = 20 if role == "iperf_train" else 60
        reps = 3 if role == "iperf_train" else 5
        for bw, rtt, q in SETTINGS:
            for cca in CCAS:
                for rep in range(reps):
                    cells.append((role, bw, rtt, q, cca, rep, dur))
    elif role == "exp11":
        for q in EXP11_Q:
            for cca in CCAS:
                for rep in range(2):
                    cells.append((role, 0.3, 275, q, cca, rep, 60))
    return cells


def main():
    cells = manifest(ROLE)
    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    todo = [
        c for c in cells if f"{c[1]}bw-{c[2]}rtt-{c[3]}q_{c[4]}_rep{c[5]}" not in done
    ]
    print(
        f"[atw:{ROLE}] {len(cells)} cells, {len(done)} done, {len(todo)} to run",
        flush=True,
    )
    t0 = time.time()
    for i, c in enumerate(todo):
        ok, tag, msg = run_cell(*c)
        if ok:
            with open(DONE, "a") as f:
                f.write(tag + "\n")
        el = time.time() - t0
        eta = (len(todo) - i - 1) * (el / (i + 1)) / 3600 if i else 0
        print(
            f"[{i+1}/{len(todo)}] {tag} {'OK ' if ok else 'FAIL'} {msg} "
            f"| ETA {eta:.1f}h",
            flush=True,
        )
    print(f"[atw:{ROLE}] done in {(time.time()-t0)/3600:.1f}h", flush=True)


if __name__ == "__main__":
    main()
