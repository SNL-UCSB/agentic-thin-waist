#!/bin/bash
# 25 receivers per room across rooms 1-2 (= 50 agents) on the 2500-CTP list.
# Network params: 5 Mbps / 10 ms / pfifo, receive-only Zoom participants.
# Uses run_files/rooms_10m600ms.env for ROOM1/ROOM2 meeting credentials.
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

NUM_ROOMS=2
SLOTS=25
MASTER=../services/orchestration/scripts/master_cosine_2500.txt
ROOMS_ENV_FILE=./rooms_10m600ms.env
STAGGER=2
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"
LOG_DIR="logs/scale25_5m10ms_test_${RUN_TAG}"
PID_DIR="pids/scale25_5m10ms_test_${RUN_TAG}"
mkdir -p "$LOG_DIR" "$PID_DIR"

for R in 1 2; do
  PORT=$(( 8015 + R ))
  for S in $(seq 1 $SLOTS); do
    RLOG="${LOG_DIR}/scale25_5m10ms_test_room${R}_slot${S}.log"
    RJL="${LOG_DIR}/scale25_5m10ms_test_room${R}_slot${S}.jsonl"
    ROOM_INDEX=$R SLOT_INDEX=$S SLOTS_PER_ROOM=$SLOTS NUM_ROOMS=$NUM_ROOMS \
      ROOMS_ENV_FILE="$ROOMS_ENV_FILE" \
      ORCH_URL=http://localhost:${PORT} \
      ZOOM_DISPLAY_NAME=Henry \
      ZOOM_CAPACITY_MBPS=5 ZOOM_LATENCY_MS=10 ZOOM_QDISC=pfifo ZOOM_WAIT_SECONDS=30 \
      SWEEP_LOG="$RJL" MASTER_CTP_LIST="$MASTER" \
      setsid python3 -u room_receiver.py > "$RLOG" 2>&1 < /dev/null &
    PID=$!; disown $PID
    echo "$PID" > "${PID_DIR}/scale25_5m10ms_test_room${R}_slot${S}.pid"
    echo "room${R} slot${S} pid=${PID}"
    sleep $STAGGER
  done
done
echo "[launch] 50 receivers launched (25/room x 2 rooms) on 2500 list at 5Mbps/10ms"
echo "[launch] run_tag=${RUN_TAG}"
echo "[launch] logs=${LOG_DIR}"
echo "[launch] pids=${PID_DIR}"
