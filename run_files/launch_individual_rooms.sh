#!/bin/bash
# Phase 1 launcher: start exactly 1 receiver agent per room (5 rooms).
#
# What it does:
#   1. Checks each per-room orchestrator (ports 8016-8020) is healthy.
#   2. Checks each broadcaster worker (ports 8101-8105) is healthy.
#      Prints a warning if a broadcaster is unreachable (non-fatal — you may
#      start them separately with broadcast_room.py).
#   3. Launches room{R}_slot1.sh for R in 1..5, staggered by 5 s.
#
# Each receiver is an independent process that walks its own CTP shard
# (master_cosine_10000_10mbps.txt lines [R-1::5]) one CTP at a time.
# Logs go to logs/room{R}_slot1.log ; resume state in logs/room{R}_slot1.jsonl.
#
# Usage:
#   cd run_files/
#   bash launch_individual_rooms.sh
#
# To watch progress:
#   tail -f logs/room*_slot1.log

set -euo pipefail
cd "$(dirname "$0")"

ROOMS=5
STAGGER_SECS=5

# ── 1. Preflight: per-room orchestrators ─────────────────────────────────────
echo "[launch] Checking per-room orchestrators …"
all_ok=1
for R in $(seq 1 $ROOMS); do
    PORT=$(( 8015 + R ))
    if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        echo "  [launch] orchestration-room${R} :${PORT}  ✓"
    else
        echo "  [launch] orchestration-room${R} :${PORT}  ✗ NOT HEALTHY"
        all_ok=0
    fi
done
if [[ $all_ok -eq 0 ]]; then
    echo "[launch] One or more per-room orchestrators unreachable."
    echo "[launch] Start them with:  docker compose --profile roomsx up -d"
    echo "[launch] Proceeding anyway — room_receiver.py will retry for ~2 min."
fi

# ── 2. Preflight: broadcaster workers ────────────────────────────────────────
echo "[launch] Checking broadcaster workers …"
for R in $(seq 1 $ROOMS); do
    PORT=$(( 8100 + R ))
    if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        echo "  [launch] broadcaster-room${R} :${PORT}  ✓"
    else
        echo "  [launch] broadcaster-room${R} :${PORT}  ✗ (not running — start separately)"
    fi
done

# ── 3. Launch 1 receiver per room ────────────────────────────────────────────
echo ""
echo "[launch] Starting 1 receiver slot per room (Phase 1) …"
mkdir -p logs pids

for R in $(seq 1 $ROOMS); do
    LOG="logs/room${R}_slot1.log"
    PID_FILE="pids/room${R}_slot1.pid"
    setsid bash "room${R}_slot1.sh" > "$LOG" 2>&1 < /dev/null &
    PID=$!
    disown $PID
    echo $PID > "$PID_FILE"
    echo "  [launch] room${R} slot1  pid=${PID}  log=${LOG}"
    if [[ $R -lt $ROOMS ]]; then
        sleep $STAGGER_SECS
    fi
done

echo ""
echo "[launch] All 5 receivers launched (Phase 1)."
echo "[launch] Monitor:  tail -f logs/room*_slot1.log"
echo "[launch] Scale up: bash scale_agents.sh <extra_slots_per_room>"
echo "[launch] Stop all: bash stop_receivers.sh"
