#!/bin/bash
# Re-run only failed/skipped CTPs from a prior missingpcap_5m10ms run.
#
# "failed/skipped" policy:
# - include CTPs whose latest status in SOURCE_MISSING_RUN_DIR is not "complete"
# - include CTPs present in MASTER_SOURCE_LIST but never seen in SOURCE_MISSING_RUN_DIR
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
ROOMS_ENV_FILE=./rooms_10m600ms.env
STAGGER=2

SOURCE_MISSING_RUN_DIR="${SOURCE_MISSING_RUN_DIR:-logs/missingpcap_5m10ms_20260618_050001}"
MASTER_SOURCE_LIST="${MASTER_SOURCE_LIST:-logs/missing_5m10ms_ctps_from_telemetry.txt}"
RETRY_LIST="${RETRY_LIST:-logs/missing_5m10ms_retry_failed_or_skipped.txt}"

if [ ! -d "$SOURCE_MISSING_RUN_DIR" ]; then
  echo "[error] SOURCE_MISSING_RUN_DIR not found: $SOURCE_MISSING_RUN_DIR"
  exit 1
fi
if [ ! -f "$MASTER_SOURCE_LIST" ]; then
  echo "[error] MASTER_SOURCE_LIST not found: $MASTER_SOURCE_LIST"
  exit 1
fi

export SOURCE_MISSING_RUN_DIR MASTER_SOURCE_LIST RETRY_LIST
python3 - <<'PY'
import glob
import json
import os
from collections import Counter
from datetime import datetime

run_dir = os.environ["SOURCE_MISSING_RUN_DIR"]
master_path = os.environ["MASTER_SOURCE_LIST"]
retry_path = os.environ["RETRY_LIST"]

master = [ln.strip() for ln in open(master_path, "r", errors="ignore") if ln.strip()]
master_set = set(master)

latest = {}
for f in glob.glob(os.path.join(run_dir, "*.jsonl")):
    with open(f, "r", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ctp = r.get("ctp_name")
            if not ctp:
                continue
            st = str(r.get("status", "")).lower()
            ts_raw = r.get("timestamp")
            try:
                ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.min
            except Exception:
                ts = datetime.min
            prev = latest.get(ctp)
            if prev is None or ts >= prev[0]:
                latest[ctp] = (ts, st)

retry = set()
for ctp in master:
    prev = latest.get(ctp)
    if prev is None:
        retry.add(ctp)  # skipped/unattempted
    elif prev[1] != "complete":
        retry.add(ctp)  # failed/timeout/etc.

os.makedirs(os.path.dirname(retry_path), exist_ok=True)
with open(retry_path, "w") as fh:
    for ctp in sorted(retry):
        fh.write(ctp + "\n")

status_counts = Counter(st for _, st in latest.values())
print(f"[retry] master_ctps={len(master)}")
print(f"[retry] seen_in_source={len(latest)}")
print(f"[retry] source_status_counts={dict(status_counts)}")
print(f"[retry] retry_ctps={len(retry)}")
print(f"[retry] list={retry_path}")
PY

if [ ! -s "$RETRY_LIST" ]; then
  echo "[launch] retry list empty; nothing to launch."
  exit 0
fi

RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"
LOG_DIR="logs/missingpcap_5m10ms_retry_${RUN_TAG}"
PID_DIR="pids/missingpcap_5m10ms_retry_${RUN_TAG}"
mkdir -p "$LOG_DIR" "$PID_DIR"

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="${LOG_DIR}/missingpcap_5m10ms_retry_room${R}_slot${S}.log"
    RJL="${LOG_DIR}/missingpcap_5m10ms_retry_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ROOMS_ENV_FILE="$ROOMS_ENV_FILE" \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=5 ZOOM_LATENCY_MS=10 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$RETRY_LIST" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "${PID_DIR}/missingpcap_5m10ms_retry_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done

echo "[launch] 50 receivers launched on missingpcap retry-failed/skipped list (5Mbps/10ms)"
echo "[launch] run_tag=${RUN_TAG}"
echo "[launch] logs=${LOG_DIR}"
echo "[launch] pids=${PID_DIR}"
