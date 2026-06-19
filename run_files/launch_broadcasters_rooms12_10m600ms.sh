#!/bin/bash
# Start long-lived broadcasters for room1 + room2 using rooms_10m600ms.env.
# This only joins the meetings (no CTP replay/capture).
set -u
cd "$(dirname "$0")"
mkdir -p logs pids

ROOMS_ENV_FILE=./rooms_10m600ms.env
WAIT_SECONDS="${1:-1000000}"

for R in 1 2; do
  LOG="logs/bcast_10m600ms_room${R}.log"
  ROOMS_ENV_FILE="$ROOMS_ENV_FILE" ROOM_INDEX=$R ZOOM_WAIT_SECONDS="$WAIT_SECONDS" \
    setsid python3 -u ../services/orchestration/scripts/broadcast_room.py > "$LOG" 2>&1 < /dev/null &
  PID=$!; disown $PID
  echo "$PID" > "pids/bcast_10m600ms_room${R}.pid"
  echo "broadcaster room${R} pid=${PID} log=${LOG}"
done

echo "[launch] broadcasters launched for rooms 1 and 2 (wait=${WAIT_SECONDS}s)"
