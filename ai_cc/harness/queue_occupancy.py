#!/usr/bin/env python3
"""Derive bottleneck queue-occupancy time series from a mahimahi mm-link
downlink log.

mm-link logs each packet event on the shaped link (relative ms timestamps):
    <ts> + <bytes>          arrival (enqueued)
    <ts> - <bytes> <delay>  departure (delivered off the link)
    <ts> d <bytes>          drop (queue full, droptail)
Occupancy(t) = cumulative arrivals - cumulative departures (drops are logged
instead of an arrival, so they never enter the queue). We reconstruct the step
function and resample it onto a uniform grid.

Usage: queue_occupancy.py <downlink.log> <hz> > queue_occupancy.csv
"""
import sys


def main():
    path, hz = sys.argv[1], float(sys.argv[2])
    events = []  # (t_ms, dpkts, dbytes)
    t_min, t_max = None, None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                ts = float(parts[0])
            except ValueError:
                continue
            ev = parts[1]
            nbytes = int(parts[2])
            if ev == "+":
                events.append((ts, +1, +nbytes))
            elif ev == "-":
                events.append((ts, -1, -nbytes))
            elif ev == "d":
                continue  # dropped, never enqueued
            else:
                continue
            t_min = ts if t_min is None else min(t_min, ts)
            t_max = ts if t_max is None else max(t_max, ts)

    if not events:
        sys.exit("no packet events parsed")
    events.sort(key=lambda e: e[0])

    step = 1000.0 / hz  # ms
    grid = []
    t = 0.0
    while t <= t_max:
        grid.append(t)
        t += step

    occ_p = occ_b = 0
    gi = 0
    rows = []
    # walk events, emit grid samples with the occupancy in effect at grid time
    ei = 0
    n = len(events)
    for gt in grid:
        while ei < n and events[ei][0] <= gt:
            occ_p += events[ei][1]
            occ_b += events[ei][2]
            if occ_p < 0:
                occ_p = 0
            if occ_b < 0:
                occ_b = 0
            ei += 1
        rows.append((gt / 1000.0, occ_p, occ_b))

    out = ["time_s,occupancy_pkts,occupancy_bytes"]
    for ts, p, b in rows:
        out.append(f"{ts:.3f},{p},{b}")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
