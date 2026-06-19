#!/bin/bash
# Scale test: 15 receivers per room across rooms 1-2 (= 30 agents) on the
# 5000-CTP master list. Sharding: NUM_ROOMS=2, SLOTS_PER_ROOM=15, total=30,
# each agent walks master_cosine_5000[g::30] (~166 CTPs, no overlap).
#
# Light 2s stagger at launch: the 10s sync boundary governs steady-state
# firing regardless, but launching 30 Chrome cold-starts simultaneously would
# spike load hard at t=0. A small stagger smooths the startup herd only.
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=15
MASTER=../services/orchestration/scripts/master_cosine_5000.txt
STAGGER=2

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="logs/scale15_room${R}_slot${S}.log"
    RJL="logs/scale15_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=10 ZOOM_LATENCY_MS=10 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MASTER" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "pids/scale15_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done
echo "[launch] 30 receivers launched (15/room x 2 rooms) on 5000 list"
