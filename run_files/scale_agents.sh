#!/bin/bash
# Add N more receiver slots spread evenly across all 5 rooms.
#
# Usage:
#   bash scale_agents.sh <slots_to_add>
#
# Examples:
#   bash scale_agents.sh 5    # → 2 slots/room  (total 10 processes)
#   bash scale_agents.sh 20   # → 5 slots/room  (total 25 processes)
#
# The script:
#   1. Reads the highest SLOT_INDEX already running (from pids/).
#   2. Generates shell stubs room{R}_slot{S}.sh for each new slot.
#   3. Launches them with a 3 s stagger.
#
# New stubs use the same SLOTS_PER_ROOM (existing + new) so that sharding is
# recalculated correctly across all live processes.  Already-running processes
# keep their original SLOTS_PER_ROOM env; you only need to restart them if you
# want full redistribution.  For most experiments the new slots simply fill in
# gaps in the CTP shard (CTPs not yet started by slot 1).

set -euo pipefail
cd "$(dirname "$0")"

ROOMS=5
STAGGER_SECS=3
CAPACITY_MBPS=10
LATENCY_MS=10
QDISC=pfifo
WAIT_SECONDS=30

if [[ $# -lt 1 ]]; then
    echo "Usage: bash scale_agents.sh <slots_to_add>"
    exit 1
fi

ADD=$1
if [[ $ADD -le 0 ]]; then
    echo "slots_to_add must be > 0"
    exit 1
fi

mkdir -p pids logs

# Detect highest current slot index from existing PID files
MAX_SLOT=0
for pid_file in pids/room*_slot*.pid; do
    [[ -f "$pid_file" ]] || continue
    S=$(basename "$pid_file" | sed 's/room[0-9]*_slot\([0-9]*\)\.pid/\1/')
    (( S > MAX_SLOT )) && MAX_SLOT=$S
done

NEW_MAX=$(( MAX_SLOT + ADD ))
echo "[scale] Current max slot: ${MAX_SLOT}  Adding: ${ADD}  New max: ${NEW_MAX}"
echo "[scale] Generating stubs for slots $((MAX_SLOT+1)) .. ${NEW_MAX} …"

for S in $(seq $((MAX_SLOT + 1)) $NEW_MAX); do
    for R in $(seq 1 $ROOMS); do
        PORT=$(( 8015 + R ))
        STUB="room${R}_slot${S}.sh"
        cat > "$STUB" << SHELLEOF
#!/bin/bash
# Individual receive-only receiver — room ${R}, slot ${S} of ${NEW_MAX}.
# ${CAPACITY_MBPS} Mbps / ${LATENCY_MS} ms / ${QDISC} / ${WAIT_SECONDS} s hold / Henry.
cd "\$(dirname "\$0")"
ROOM_INDEX=${R} SLOT_INDEX=${S} SLOTS_PER_ROOM=${NEW_MAX} NUM_ROOMS=${ROOMS} \\
  ORCH_URL=http://localhost:${PORT} \\
  ZOOM_DISPLAY_NAME=Henry \\
  ZOOM_CAPACITY_MBPS=${CAPACITY_MBPS} ZOOM_LATENCY_MS=${LATENCY_MS} \\
  ZOOM_QDISC=${QDISC} ZOOM_WAIT_SECONDS=${WAIT_SECONDS} \\
  MASTER_CTP_LIST=../services/orchestration/scripts/master_cosine_10000_10mbps.txt \\
  exec python3 -u room_receiver.py "\$@"
SHELLEOF
        chmod +x "$STUB"
    done
done

echo "[scale] Launching ${ADD} new slots across ${ROOMS} rooms …"
for S in $(seq $((MAX_SLOT + 1)) $NEW_MAX); do
    for R in $(seq 1 $ROOMS); do
        STUB="room${R}_slot${S}.sh"
        LOG="logs/room${R}_slot${S}.log"
        PID_FILE="pids/room${R}_slot${S}.pid"
        setsid bash "$STUB" > "$LOG" 2>&1 < /dev/null &
        PID=$!
        disown $PID
        echo $PID > "$PID_FILE"
        echo "  [scale] room${R} slot${S}  pid=${PID}  log=${LOG}"
        sleep $STAGGER_SECS
    done
done

TOTAL=$(( NEW_MAX * ROOMS ))
echo ""
echo "[scale] Done.  Total receiver processes now: ${TOTAL} (${NEW_MAX} slots × ${ROOMS} rooms)."
echo "[scale] Monitor: tail -f logs/room*_slot*.log"
