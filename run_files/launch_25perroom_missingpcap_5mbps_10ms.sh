#!/bin/bash
# Re-run only missing-PCAP CTPs for the completed 5Mbps/10ms run.
# It computes the missing set from run JSONL + telemetry DB/artifacts, then
# launches 25 receivers per room (rooms 1-2) over that reduced list.
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
ROOMS_ENV_FILE=./rooms_10m600ms.env
STAGGER=2

# Source run to inspect (override when needed)
SOURCE_RUN_DIR="${SOURCE_RUN_DIR:-logs/scale25_5m10ms_test_20260617_234815}"
MISSING_LIST="${MISSING_LIST:-logs/missing_5m10ms_ctps_from_telemetry.txt}"

# Telemetry DB connection (defaults match current compose setup)
TELEMETRY_DB_HOST="${TELEMETRY_DB_HOST:-localhost}"
TELEMETRY_DB_PORT="${TELEMETRY_DB_PORT:-5433}"
TELEMETRY_DB_NAME="${TELEMETRY_DB_NAME:-telemetry}"
TELEMETRY_DB_USER="${TELEMETRY_DB_USER:-admin}"
TELEMETRY_DB_PASSWORD="${TELEMETRY_DB_PASSWORD:-admin123}"

if [ ! -d "$SOURCE_RUN_DIR" ]; then
  echo "[error] SOURCE_RUN_DIR not found: $SOURCE_RUN_DIR"
  exit 1
fi

export SOURCE_RUN_DIR MISSING_LIST
export TELEMETRY_DB_HOST TELEMETRY_DB_PORT TELEMETRY_DB_NAME
export TELEMETRY_DB_USER TELEMETRY_DB_PASSWORD

python3 - <<'PY'
import glob
import json
import os
import sys
from collections import defaultdict

import psycopg2

source_dir = os.environ["SOURCE_RUN_DIR"]
missing_list = os.environ["MISSING_LIST"]

db_host = os.environ["TELEMETRY_DB_HOST"]
db_port = int(os.environ["TELEMETRY_DB_PORT"])
db_name = os.environ["TELEMETRY_DB_NAME"]
db_user = os.environ["TELEMETRY_DB_USER"]
db_password = os.environ["TELEMETRY_DB_PASSWORD"]

rows = []
for f in glob.glob(os.path.join(source_dir, "*.jsonl")):
    with open(f, "r", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

if not rows:
    print(f"[error] no JSONL records found in {source_dir}")
    sys.exit(1)

complete_rows = [r for r in rows if r.get("status") == "complete"]
missing_ctps = set()

# 1) Any non-complete status from source run => include CTP for rerun
for r in rows:
    if r.get("status") != "complete":
        ctp = r.get("ctp_name")
        if ctp:
            missing_ctps.add(ctp)

# 2) Complete rows missing experiment_id => include CTP
complete_with_expid = []
for r in complete_rows:
    if r.get("experiment_id"):
        complete_with_expid.append(r)
    else:
        ctp = r.get("ctp_name")
        if ctp:
            missing_ctps.add(ctp)

exp_to_rows = defaultdict(list)
for r in complete_with_expid:
    exp_to_rows[r["experiment_id"]].append(r)

exp_ids = sorted(exp_to_rows.keys())

conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
)
cur = conn.cursor()

# Map experiment_id -> result_id (if present in telemetry)
exp_to_result = {}
if exp_ids:
    cur.execute(
        """
        SELECT experiment_id, result_id
        FROM results
        WHERE experiment_id = ANY(%s)
        """,
        (exp_ids,),
    )
    for experiment_id, result_id in cur.fetchall():
        exp_to_result[experiment_id] = result_id

# Missing result rows => include corresponding CTP(s)
for exp_id in exp_ids:
    if exp_id not in exp_to_result:
        for r in exp_to_rows[exp_id]:
            ctp = r.get("ctp_name")
            if ctp:
                missing_ctps.add(ctp)

# Check pcap artifacts for present result rows
result_ids = [rid for rid in exp_to_result.values()]
art_by_result = defaultdict(list)
if result_ids:
    cur.execute(
        """
        SELECT result_id, artifact_type, filename
        FROM artifacts
        WHERE result_id = ANY(%s)
        """,
        (result_ids,),
    )
    for result_id, artifact_type, filename in cur.fetchall():
        art_by_result[result_id].append(
            ((artifact_type or "").lower(), (filename or "").lower())
        )

def has_pcap_art(arts):
    for atype, fname in arts:
        if atype == "pcap":
            return True
        if fname.endswith(".pcap") or fname.endswith(".pcapng"):
            return True
    return False

for exp_id, result_id in exp_to_result.items():
    if not has_pcap_art(art_by_result.get(result_id, [])):
        for r in exp_to_rows[exp_id]:
            ctp = r.get("ctp_name")
            if ctp:
                missing_ctps.add(ctp)

cur.close()
conn.close()

ordered = sorted(missing_ctps)
os.makedirs(os.path.dirname(missing_list), exist_ok=True)
with open(missing_list, "w") as fh:
    for ctp in ordered:
        fh.write(ctp + "\n")

print(f"[missing] source_records={len(rows)}")
print(f"[missing] complete_rows={len(complete_rows)}")
print(f"[missing] missing_ctps={len(ordered)}")
print(f"[missing] list={missing_list}")
PY

if [ ! -s "$MISSING_LIST" ]; then
  echo "[error] Missing list is empty: $MISSING_LIST"
  exit 1
fi

RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"
LOG_DIR="logs/missingpcap_5m10ms_${RUN_TAG}"
PID_DIR="pids/missingpcap_5m10ms_${RUN_TAG}"
mkdir -p "$LOG_DIR" "$PID_DIR"

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="${LOG_DIR}/missingpcap_5m10ms_room${R}_slot${S}.log"
    RJL="${LOG_DIR}/missingpcap_5m10ms_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ROOMS_ENV_FILE="$ROOMS_ENV_FILE" \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=5 ZOOM_LATENCY_MS=10 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MISSING_LIST" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "${PID_DIR}/missingpcap_5m10ms_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done

echo "[launch] 50 receivers launched (25/room x 2 rooms) on missing-pcap 5Mbps/10ms list"
echo "[launch] run_tag=${RUN_TAG}"
echo "[launch] logs=${LOG_DIR}"
echo "[launch] pids=${PID_DIR}"
