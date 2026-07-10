#!/usr/bin/env bash
# Background campaign: run all 20 cells sequentially through run_one.sh, logging
# progress. Designed to survive disconnect (launch via setsid/nohup).
set -u
ROOT=/home/jaber/agentic-thin-waist
TROOT=$ROOT/atw_cc_timing
LOG=$TROOT/campaign.log
DUR=60
echo "=== campaign start $(date -u +%FT%TZ) pid=$$ ===" >> "$LOG"
n=0; ok=0
while read -r IDX BW RTT Q CC; do
  [ -z "${IDX:-}" ] && continue
  n=$((n+1))
  echo "--- [$n/20] cell idx=$IDX $BW/$RTT/$Q/$CC $(date -u +%FT%TZ) ---" >> "$LOG"
  bash "$TROOT/harness/run_one.sh" "$IDX" "$BW" "$RTT" "$Q" "$CC" "$DUR" >> "$LOG" 2>&1
  # mark done
  ST=$(grep -m1 '^final_status=' "$TROOT/runs/"*"_${BW}bw-${RTT}rtt-${Q}q_${CC}/phases.env" 2>/dev/null | head -1 | cut -d= -f2)
  [ "$ST" = complete ] && ok=$((ok+1))
  echo "    -> final=$ST (ok so far: $ok/$n)" >> "$LOG"
done < "$TROOT/harness/cells.txt"
# reset host CC to a sane default
sudo -n sysctl -w net.ipv4.tcp_congestion_control=cubic >/dev/null 2>&1
echo "=== campaign done $(date -u +%FT%TZ) completed=$ok/$n ===" >> "$LOG"
# aggregate
python3 "$TROOT/harness/aggregate.py" >> "$LOG" 2>&1
echo "=== aggregate done $(date -u +%FT%TZ) ===" >> "$LOG"
touch "$TROOT/CAMPAIGN_DONE"
