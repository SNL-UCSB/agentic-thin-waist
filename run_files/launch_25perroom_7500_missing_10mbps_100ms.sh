#!/bin/bash
# Rerun 50 receivers on CTPs missing telemetry PCAP (3518-entry list).
# Fresh jsonl logs so prior "complete" rows do not skip upload-failed CTPs.
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
MASTER=../services/orchestration/scripts/master_cosine_7500_10mbps_missing_telemetry_pcap.txt
ROOMS_ENV_FILE=./rooms_10m600ms.env
STAGGER=2

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="logs/scale25_10m100ms_7500_missing_room${R}_slot${S}.log"
    RJL="logs/scale25_10m100ms_7500_missing_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ROOMS_ENV_FILE="$ROOMS_ENV_FILE" \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=10 ZOOM_LATENCY_MS=100 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MASTER" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "pids/scale25_10m100ms_7500_missing_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done
echo "[launch] 50 receivers on missing-telemetry list (3518 CTPs) at 10Mbps/100ms"
