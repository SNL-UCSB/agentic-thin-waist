#!/usr/bin/env python3
"""Run the CPUC demo: shaped YouTube VoD with player stats, pcap and qtrace.

Drives the substrate worker (:8002) directly so the run gets all three signals
at once:

  * pcap      -- download throughput (tshark on veth2)
  * qtrace    -- bottleneck queue occupancy + drops (leaf-qdisc sampler)
  * player    -- YouTube Stats-for-nerds via NetGent's `youtube_stats` action

Everything lands in one directory that cpuc_demo.ipynb reads:

    cpuc_runs/<run_name>/{run.json,capture.pcap,qtrace.jsonl,meta.json}

Usage:
    python3 cpuc_demo_run.py                       # 6 Mbps / 100 ms / 32 pkt, 60 s
    python3 cpuc_demo_run.py --watch-seconds 600   # full Prudentia duration
    python3 cpuc_demo_run.py --mbps 10 --latency-ms 50 --buffer-packets 64
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKER = os.environ.get("WORKER_URL", "http://localhost:8002")
WORKFLOW = (
    HERE
    / "shared/clients/netgent/scripts/workflow"
    / "prudentia_youtube_vod_stats_workflow.json"
)


def _req(method, path, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(
        WORKER + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> HTTP {e.code}\n{e.read().decode()[:800]}")
    return json.loads(body.decode()) if body else {}


def _download(path, dest, timeout=120):
    req = urllib.request.Request(WORKER + path, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dest.write_bytes(r.read())
    return dest.stat().st_size


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mbps", type=float, default=6.0, help="bottleneck capacity")
    p.add_argument(
        "--latency-ms", type=float, default=100.0, help="added one-way latency"
    )
    p.add_argument("--buffer-packets", type=int, default=32, help="pfifo queue limit")
    p.add_argument("--qdisc", default="pfifo")
    p.add_argument("--cca", default="cubic")
    p.add_argument("--watch-seconds", type=int, default=60, help="playback duration")
    p.add_argument(
        "--interval-seconds", type=float, default=1.0, help="player poll period"
    )
    p.add_argument(
        "--nerd-stats-every",
        type=int,
        default=5,
        help="call getStatsForNerds() every Nth sample",
    )
    p.add_argument(
        "--video-id", default="aqz-KE-bpKQ", help="Big Buck Bunny by default"
    )
    p.add_argument("--run-name", default=None)
    p.add_argument("--out-dir", default=str(HERE / "cpuc_runs"))
    args = p.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = args.run_name or (
        f"yt_{args.mbps:g}bw-{args.latency_ms:g}rtt-{args.buffer_packets}q"
        f"_{args.cca}_{stamp}"
    )
    run_dir = Path(args.out_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    samples = max(int(args.watch_seconds / args.interval_seconds), 1)
    workflow = json.loads(WORKFLOW.read_text())
    workflow["states"][0]["actions"][-1]["params"]["nerd_stats_every"] = str(
        args.nerd_stats_every
    )

    print(f"run dir : {run_dir}")
    print(
        f"regime  : {args.mbps:g} Mbps / {args.latency_ms:g} ms / "
        f"{args.qdisc} {args.buffer_packets} pkt / {args.cca}"
    )
    bdp = args.mbps * 1e6 * (args.latency_ms / 1000.0) / 8 / 1500
    print(f"BDP     : {bdp:.1f} pkt -> buffer is {args.buffer_packets / bdp:.2f}x BDP")
    print(
        f"playback: {args.watch_seconds}s, {samples} samples @ {args.interval_seconds}s"
    )

    # 1. Shape the bottleneck up front so capture/qtrace observe the real regime.
    print("\n[1/5] shaping...")
    shape = _req(
        "POST",
        "/shape",
        {
            "upstream_iface": "veth4",
            "downstream_iface": "veth2",
            "download_mbps": args.mbps,
            "upload_mbps": args.mbps,
            "latency_ms": args.latency_ms,
            "qdisc": args.qdisc,
            "buffer_packets": args.buffer_packets,
            "verify": False,  # an iperf3 self-test would pollute the pcap
        },
        timeout=180,
    )
    print("      ", shape.get("status"))

    # 2/3. Start capture + qtrace before the browser so nothing is missed.
    #
    # The capture gets an explicit duration: `DELETE /capture/{id}` both stops
    # tshark AND deregisters the session, after which `/pcap` 404s -- so the
    # capture has to self-terminate on its own timer, leaving the session
    # around long enough to download from. (qtrace's DELETE deliberately keeps
    # its session, so it needs no such trick.)
    capture_seconds = args.watch_seconds + 20
    print("[2/5] starting capture + qtrace...")
    cap = _req(
        "POST",
        "/capture",
        {
            "interface": "veth2",
            "filename": f"{run_name}.pcap",
            "duration_seconds": capture_seconds,
        },
    )
    qt = _req(
        "POST",
        "/qtrace",
        {
            "interfaces": ["veth2", "veth4"],
            "filename": f"{run_name}.jsonl",
            "interval_ms": 20,
        },
    )
    print(f"       capture_id={cap['capture_id']}  qtrace_id={qt['qtrace_id']}")

    # 4. Run the workflow. /run re-applies the same shaping, which is a no-op
    #    here but keeps this call self-describing.
    print(f"[3/5] playing {args.watch_seconds}s...")
    t0 = time.time()
    run = _req(
        "POST",
        "/run",
        {
            "upstream_iface": "veth4",
            "downstream_iface": "veth2",
            "download_mbps": args.mbps,
            "upload_mbps": args.mbps,
            "latency_ms": args.latency_ms,
            "qdisc": args.qdisc,
            "buffer_packets": args.buffer_packets,
            "cca": args.cca,
            "verify_shaping": False,
            "workflow": workflow,
            "runtime": "browser",
            "parameters": {
                "video_id": args.video_id,
                "samples": str(samples),
                "interval_seconds": str(args.interval_seconds),
            },
            "experiment_max_seconds": args.watch_seconds + 120,
        },
        timeout=args.watch_seconds + 400,
    )
    wall = time.time() - t0
    print(f"       done in {wall:.1f}s")

    # 5. Stop the collectors and pull their artifacts down.
    print("[4/5] stopping collectors...")
    qstop = _req("DELETE", f"/qtrace/{qt['qtrace_id']}")
    print(f"       qtrace samples: {qstop.get('samples_written')}")

    # tshark must exit before the pcap is finalized and downloadable.
    deadline = time.time() + capture_seconds + 30
    while time.time() < deadline:
        status = _req("GET", f"/capture/{cap['capture_id']}")
        if status.get("exit_code") is not None:
            break
        remaining = int(deadline - time.time())
        print(
            f"       waiting for capture to finalize ({remaining}s left)...", end="\r"
        )
        time.sleep(2)
    print(" " * 60, end="\r")

    print("[5/5] downloading artifacts...")
    pcap_path = run_dir / "capture.pcap"
    qtrace_path = run_dir / "qtrace.jsonl"
    n_pcap = _download(f"/capture/{cap['capture_id']}/pcap", pcap_path, timeout=300)
    n_qt = _download(f"/qtrace/{qt['qtrace_id']}/trace", qtrace_path, timeout=300)
    _req("DELETE", f"/capture/{cap['capture_id']}")  # deregister only now
    print(
        f"       {pcap_path.name}: {n_pcap/1e6:.2f} MB   {qtrace_path.name}: {n_qt/1e3:.0f} kB"
    )

    # Screenshots are base64 PNGs on every action — huge and useless here.
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if k not in ("screenshot", "har")}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    (run_dir / "run.json").write_text(json.dumps(strip(run), indent=2))
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_name": run_name,
                "timestamp": stamp,
                "capacity_mbps": args.mbps,
                "latency_ms": args.latency_ms,
                "buffer_packets": args.buffer_packets,
                "qdisc": args.qdisc,
                "cca": args.cca,
                "video_id": args.video_id,
                "watch_seconds": args.watch_seconds,
                "samples_requested": samples,
                "interval_seconds": args.interval_seconds,
                "nerd_stats_every": args.nerd_stats_every,
                "wall_seconds": round(wall, 1),
                "bdp_packets": round(bdp, 1),
                "shape": shape,
            },
            indent=2,
        )
    )

    # Surface the headline player stats so a failed collection is obvious now,
    # not after opening the notebook.
    stats = None
    try:
        for action in strip(run)["result"][0]["output"][0]:
            if isinstance(action, dict) and "sample_count" in action:
                stats = action
    except (KeyError, IndexError, TypeError):
        pass

    print(f"\nwrote {run_dir}")
    if stats:
        got, want = stats.get("collected_count"), stats.get("sample_count")
        print(f"player samples : {got}/{samples} requested")
        for k in (
            "resolution",
            "optimal_res",
            "codecs",
            "itag",
            "buffer_health",
            "dropped_frames_total",
            "total_frames",
            "bandwidth_kbps",
            "playback_quality",
            "resolutions_seen",
            "resolution_switches",
        ):
            if stats.get(k) is not None:
                print(f"  {k:22s}: {stats[k]}")
        if stats.get("stopped_early"):
            print(f"\n  !! {stats['stopped_early']}")
            print("     The browser session ended before the watch window did.")
            print("     See the browserless timeout note in cpuc_demo.md.")
    else:
        print("player samples : none (no youtube_stats output in the response)")

    print(
        f"\nNow open the notebook:\n    RUN_DIR={run_dir} jupyter lab cpuc_demo.ipynb"
    )


if __name__ == "__main__":
    main()
