#!/usr/bin/env python3
"""Generate a constant-bitrate mahimahi link trace.

A mahimahi trace is a list of millisecond timestamps; each line is one
opportunity to send a single 1500-byte (MTU) packet. mm-link loops the file.
For a rate R (Mbps): packets/ms = R*1e6 / (8 * 1500 * 1000).

Usage: gen_trace.py <rate_mbps> <duration_ms> > trace
"""
import sys

MTU = 1500  # bytes, mahimahi accounting unit


def main():
    rate_mbps = float(sys.argv[1])
    dur_ms = int(sys.argv[2])
    pkts_per_ms = rate_mbps * 1e6 / (8 * MTU * 1000)
    n = round(pkts_per_ms * dur_ms)
    out = []
    for i in range(1, n + 1):
        ts = round(i / pkts_per_ms)
        if ts < 1:
            ts = 1
        if ts > dur_ms:
            ts = dur_ms
        out.append(str(ts))
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
