#!/bin/bash
# 25 receivers per room across rooms 1-2 (= 50 agents) on the missing-pcap list.
# Sharding: NUM_ROOMS=2, SLOTS_PER_ROOM=25, total=50, each agent walks
# missing_100m10ms_ctps_from_telemetry[g::50] (~10-11 CTPs, no overlap).
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
MASTER=logs/missing_100m10ms_ctps_from_telemetry.txt
STAGGER=2

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="logs/missingpcap_100m10ms_room${R}_slot${S}.log"
    RJL="logs/missingpcap_100m10ms_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=100 ZOOM_LATENCY_MS=10 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MASTER" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "pids/missingpcap_100m10ms_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done
echo "[launch] 50 receivers launched (25/room x 2 rooms) on missing-pcap 100Mbps/10ms list"
