#!/usr/bin/env python3
"""Verify the N most-recent receiver experiments are persisted in telemetry.

For each experiment_id (taken from the receiver jsonl, newest first) we query
telemetry GET /results?experiment_id=... and then /results/{id}/artifacts to
confirm a result row + pcap artifact exist.
"""
import glob
import json
import sys
import requests

TELE = "http://localhost:8004"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30

rows = []
for f in glob.glob("logs/scale15_room*_slot*.jsonl"):
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
recent = rows[:N]
print(f"checking {len(recent)} most-recent experiments against telemetry\n")

ok = 0
missing = []
no_pcap = []
for r in recent:
    eid = r.get("experiment_id")
    try:
        resp = requests.get(f"{TELE}/results", params={"experiment_id": eid, "limit": 5}, timeout=30)
        data = resp.json()
        results = data.get("results", [])
    except Exception as exc:
        results = []
        print(f"  ERR querying {eid}: {exc}")
    if not results:
        missing.append(eid)
        print(f"  MISSING   {eid}")
        continue
    res = results[0]
    rid = res.get("result_id")
    pcap = res.get("pcap_path")
    status = res.get("status")
    # check artifacts
    art_n = 0
    try:
        a = requests.get(f"{TELE}/results/{rid}/artifacts", timeout=30).json()
        art_n = len(a.get("artifacts", []))
    except Exception:
        pass
    pcap_ok = bool(pcap)
    if not pcap_ok and art_n == 0:
        no_pcap.append(eid)
    flag = "OK " if (pcap_ok or art_n) else "NOPCAP"
    if pcap_ok or art_n:
        ok += 1
    print(f"  {flag} status={status} artifacts={art_n} {eid}")

print(f"\nSUMMARY: {ok}/{len(recent)} have result+pcap/artifact in telemetry")
if missing:
    print(f"  {len(missing)} MISSING from telemetry: {missing}")
if no_pcap:
    print(f"  {len(no_pcap)} present but NO pcap/artifact: {no_pcap}")
