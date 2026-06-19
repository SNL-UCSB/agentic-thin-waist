#!/bin/bash
# Start all 50 async receive-only workers (10 per room x 5 rooms), 10 Mbps/100 ms.
# Staggered 3s each so the create cap (10/orchestrator) isn't slammed instantly.
cd "$(dirname "$0")"
for r in 1 2 3 4 5; do
  for w in 01 02 03 04 05 06 07 08 09 10; do
    f="room${r}_worker${w}.sh"
    setsid bash "$f" > "logs/${f%.sh}.log" 2>&1 < /dev/null &
    disown
    sleep 3
  done
done
echo "[launch_all] all 50 async workers launched"
