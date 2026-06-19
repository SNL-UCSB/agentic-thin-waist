#!/bin/bash
# Stop all running receiver processes tracked in pids/
cd "$(dirname "$0")"
STOPPED=0
for pid_file in pids/room*_slot*.pid; do
    [[ -f "$pid_file" ]] || continue
    PID=$(cat "$pid_file")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "  stopped pid=$PID  ($pid_file)"
        STOPPED=$(( STOPPED + 1 ))
    fi
    rm -f "$pid_file"
done
echo "[stop] Stopped ${STOPPED} receiver(s)."
