#!/bin/bash
# 25 receivers per room across rooms 1-2 (= 50 agents) on the 7494-CTP list
# (master_cosine_7500_10mbps.txt: full 10 Mbps corpus minus the 2500 batch).
# Sharding: NUM_ROOMS=2, SLOTS_PER_ROOM=25, total=50, each agent walks
# master[g::50] (~150 CTPs, no overlap).
# Network params: 10 Mbps / 100 ms / pfifo, receive-only Zoom participants.
# Uses run_files/rooms_10m600ms.env for ROOM1/ROOM2 meeting credentials.
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
MASTER=../services/orchestration/scripts/master_cosine_7500_10mbps.txt
ROOMS_ENV_FILE=./rooms_10m600ms.env
STAGGER=2

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="logs/scale25_10m100ms_7500_room${R}_slot${S}.log"
    RJL="logs/scale25_10m100ms_7500_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ROOMS_ENV_FILE="$ROOMS_ENV_FILE" \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=10 ZOOM_LATENCY_MS=100 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MASTER" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "pids/scale25_10m100ms_7500_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done
echo "[launch] 50 receivers launched (25/room x 2 rooms) on 7500 list at 10Mbps/100ms"
