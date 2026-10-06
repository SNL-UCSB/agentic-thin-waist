#!/usr/bin/env python3
"""Exp3 / Fig 4 — ping the CrUX Top-10K and record min-RTT for the RTT CDF.
Pure terminal (no ATW). Parallel, one ping per host, ICMP; unresponsive hosts
(many, expected) are dropped — the paper's Fig 4 is the CDF over responsive sites."""
import subprocess, re, json, os, sys
from concurrent.futures import ThreadPoolExecutor

HOSTS = open(os.path.join(os.path.dirname(__file__), "crux_top10k.txt")).read().split()
OUT = os.path.join(os.path.dirname(__file__), "ping_rtts.json")
RTT_RE = re.compile(r"min/avg/max\S* = ([\d.]+)/([\d.]+)/")


def ping(host):
    try:
        p = subprocess.run(["ping", "-c", "1", "-W", "2", host],
                           capture_output=True, text=True, timeout=6)
        m = RTT_RE.search(p.stdout)
        if m:
            return (host, float(m.group(1)))
    except Exception:
        pass
    return (host, None)


def main():
    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=100) as ex:
        for host, rtt in ex.map(ping, HOSTS):
            results[host] = rtt
            done += 1
            if done % 1000 == 0:
                ok = sum(1 for v in results.values() if v is not None)
                print(f"  pinged {done}/{len(HOSTS)}  responsive={ok}", flush=True)
    rtts = sorted(v for v in results.values() if v is not None)
    summary = {
        "experiment": "Exp3 / Fig 4 — RTT CDF of CrUX Top-10K",
        "n_hosts": len(HOSTS),
        "n_responsive": len(rtts),
        "pct_le_275ms": round(100 * sum(1 for r in rtts if r <= 275) / len(rtts), 1) if rtts else 0,
        "median_ms": rtts[len(rtts) // 2] if rtts else None,
        "rtts_ms": rtts,
    }
    with open(OUT, "w") as f:
        json.dump(summary, f)
    print(f"DONE: {len(rtts)}/{len(HOSTS)} responsive; "
          f"{summary['pct_le_275ms']}% <=275ms; wrote {OUT}")


if __name__ == "__main__":
    main()
