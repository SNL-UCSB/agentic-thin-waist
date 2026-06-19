#!/usr/bin/env bash
set -euo pipefail

# Keep one representative flow per pcap:
# - Anchor on JOINER_IP (default 172.16.1.20)
# - Exclude obvious background protocols
# - Pick the highest-packet 5-tuple (direction-agnostic)
# - Write only that flow to mirrored output path
#
# Usage:
#   ./filter_top_zoom_flow_parallel.sh [SRC_ROOT] [DST_ROOT] [WORKERS] [JOINER_IP]
#
# Example:
#   ./filter_top_zoom_flow_parallel.sh \
#     /mnt/md0/haarika/experiment_results/100_mbps_10ms \
#     /mnt/md0/haarika/experiment_results/100_mbps_10ms_topflow \
#     64 \
#     172.16.1.20

SRC_ROOT="${1:-/mnt/md0/haarika/experiment_results/100_mbps_10ms}"
DST_ROOT="${2:-/mnt/md0/haarika/experiment_results/100_mbps_10ms_topflow}"
WORKERS="${3:-128}"
JOINER_IP="${4:-172.16.1.20}"

mkdir -p "$DST_ROOT"

python3 - "$SRC_ROOT" "$DST_ROOT" "$WORKERS" "$JOINER_IP" <<'PY'
import csv
import os
import shlex
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed


def walk_pcaps(root):
    out = []
    for base, _, files in os.walk(root):
        for name in files:
            if name.endswith(".pcap") or name.endswith(".pcapng"):
                out.append(os.path.join(base, name))
    return sorted(out)


def tshark_top_flow(path, joiner_ip):
    """
    Returns:
      (flow_key, packet_count, status, note)
    flow_key is tuple: (l4, ip_a, port_a, ip_b, port_b) with canonical endpoint ordering.
    """
    display_filter = (
        f"ip.addr=={joiner_ip} && "
        "!(dns || arp || icmp || icmpv6 || mdns || dhcp)"
    )
    cmd = [
        "tshark",
        "-r",
        path,
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "separator=|",
        "-E",
        "quote=n",
        "-e",
        "ip.proto",
        "-e",
        "ip.src",
        "-e",
        "ip.dst",
        "-e",
        "tcp.srcport",
        "-e",
        "tcp.dstport",
        "-e",
        "udp.srcport",
        "-e",
        "udp.dstport",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:
        return None, 0, "tshark_error", str(exc)

    if proc.returncode != 0:
        return None, 0, "tshark_error", (proc.stderr or "").strip()

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return None, 0, "no_matching_packets", ""

    flows = Counter()
    for ln in lines:
        parts = ln.split("|")
        while len(parts) < 8:
            parts.append("")
        proto, src, dst, tcp_s, tcp_d, udp_s, udp_d = parts[:7]
        if not proto or not src or not dst:
            continue

        if proto == "6":
            l4 = "TCP"
            sp, dp = tcp_s, tcp_d
        elif proto == "17":
            l4 = "UDP"
            sp, dp = udp_s, udp_d
        else:
            # Keep non-TCP/UDP visible but without ports.
            l4 = f"IP{proto}"
            sp, dp = "", ""

        a = (src, sp)
        b = (dst, dp)
        ep1, ep2 = (a, b) if a <= b else (b, a)
        key = (l4, ep1[0], ep1[1], ep2[0], ep2[1])
        flows[key] += 1

    if not flows:
        return None, 0, "no_parsed_flows", ""

    best_key, best_pkts = flows.most_common(1)[0]
    return best_key, int(best_pkts), "ok", ""


def bpf_for_flow(flow_key):
    l4, ip1, p1, ip2, p2 = flow_key
    pair = f"(host {ip1} and host {ip2})"

    if l4 == "TCP":
        # Bidirectional exact 5-tuple.
        return (
            f"tcp and ("
            f"(src host {ip1} and src port {p1} and dst host {ip2} and dst port {p2}) or "
            f"(src host {ip2} and src port {p2} and dst host {ip1} and dst port {p1})"
            f")"
        )
    if l4 == "UDP":
        return (
            f"udp and ("
            f"(src host {ip1} and src port {p1} and dst host {ip2} and dst port {p2}) or "
            f"(src host {ip2} and src port {p2} and dst host {ip1} and dst port {p1})"
            f")"
        )

    # Generic IP protocol number.
    proto_num = l4.removeprefix("IP")
    if proto_num.isdigit():
        return f"ip proto {proto_num} and {pair}"
    return pair


def process_one(src_file, src_root, dst_root, joiner_ip):
    rel = os.path.relpath(src_file, src_root)
    dst_file = os.path.join(dst_root, rel)
    os.makedirs(os.path.dirname(dst_file), exist_ok=True)

    best_key, best_pkts, status, note = tshark_top_flow(src_file, joiner_ip)
    if status != "ok" or best_key is None:
        return {
            "src_file": src_file,
            "dst_file": "",
            "status": status,
            "note": note,
            "pkts": 0,
            "flow": "",
            "bpf": "",
        }

    bpf = bpf_for_flow(best_key)
    cmd = ["tcpdump", "-nn", "-r", src_file, "-w", dst_file, bpf]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {
            "src_file": src_file,
            "dst_file": dst_file,
            "status": "tcpdump_write_error",
            "note": (proc.stderr or "").strip(),
            "pkts": best_pkts,
            "flow": repr(best_key),
            "bpf": bpf,
        }

    # Ensure output contains at least one packet; otherwise remove.
    chk = subprocess.run(
        ["tcpdump", "-nn", "-r", dst_file, "-c", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    if chk.returncode != 0 or not (chk.stdout or "").strip():
        try:
            os.remove(dst_file)
        except OSError:
            pass
        return {
            "src_file": src_file,
            "dst_file": dst_file,
            "status": "empty_after_filter",
            "note": "",
            "pkts": best_pkts,
            "flow": repr(best_key),
            "bpf": bpf,
        }

    return {
        "src_file": src_file,
        "dst_file": dst_file,
        "status": "ok",
        "note": "",
        "pkts": best_pkts,
        "flow": repr(best_key),
        "bpf": bpf,
    }


def main():
    if len(sys.argv) != 5:
        raise SystemExit("Expected args: SRC_ROOT DST_ROOT WORKERS JOINER_IP")

    src_root, dst_root, workers_s, joiner_ip = sys.argv[1:]
    workers = max(1, int(workers_s))

    src_files = walk_pcaps(src_root)
    if not src_files:
        print("No source pcap/pcapng files found.", flush=True)
        return

    print(f"Source files: {len(src_files)}", flush=True)
    print(f"Output root: {dst_root}", flush=True)
    print(f"Joiner IP: {joiner_ip}", flush=True)
    print(f"Parallel workers: {workers}", flush=True)
    print(
        "Mode: one top packet-count flow per pcap (joiner-anchored, background excluded).",
        flush=True,
    )

    results = []
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(process_one, src_file, src_root, dst_root, joiner_ip)
            for src_file in src_files
        ]
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            done += 1
            print(
                f"[{done}/{len(src_files)}] {res['status']} pkts={res['pkts']} "
                f"src={res['src_file']}",
                flush=True,
            )

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"Completed. Output files written: {ok}/{len(results)}", flush=True)

    summary_csv = os.path.join(dst_root, "_top_flow_summary.csv")
    with open(summary_csv, "w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["src_file", "dst_file", "status", "pkts", "flow", "bpf", "note"],
        )
        w.writeheader()
        for r in sorted(results, key=lambda x: x["src_file"]):
            w.writerow(r)
    print(f"Summary: {summary_csv}", flush=True)


if __name__ == "__main__":
    main()
PY
