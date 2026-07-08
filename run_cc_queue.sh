#!/usr/bin/env bash
# run_cc_queue.sh — 3 CCAnalyzer-style runs for the cc_queue.ipynb analysis.
#
#   1) cubic  @ 10 Mbps / 85 ms  / 64-pkt pfifo
#   2) bbr    @ 10 Mbps / 275 ms / 64-pkt pfifo
#   3) reno   @ 15 Mbps / 139 ms / 64-pkt pfifo
#
# All runs: 60 s, 1 trial, wget of http://128.111.5.237:8888/1GB.bin -> /dev/null.
# For each run it sets the HOST congestion control (the file server is this host,
# the sender), submits the intent, polls to completion, downloads the pcap +
# queue-occupancy trace + result JSON into cc_results/, and appends a timing row.
#
# Needs root ONLY for `sysctl -w tcp_congestion_control` -> run with sudo:
#     sudo bash /home/jaber/agentic-thin-waist/run_cc_queue.sh
#
# No jq dependency (uses python3). Safe to re-run; each run gets a fresh
# experiment_id, artifacts are namespaced by run tag.

set -uo pipefail

REPO=/home/jaber/agentic-thin-waist
RESULTS="$REPO/cc_results"
REPORT="$REPO/cc_report.md"
ORCH=http://localhost:8005
TELE=http://localhost:8004
SUBW=http://localhost:8002
FILE_URL=http://128.111.5.237:8888/1GB.bin
DUR=60
Q=64

mkdir -p "$RESULTS"
TIMING="$RESULTS/timing.csv"
if [ ! -f "$TIMING" ]; then
  echo "experiment_id,cc,bw_mbps,rtt_ms,queue_pkts,declared_duration_s,t_submit_epoch,t_finish_epoch,wall_s,status" > "$TIMING"
fi

log_issue() { echo "$(date -Iseconds) | $1" >> "$REPORT"; echo "  [issue logged] $1"; }

# JSON field extractor: reads stdin, prints python-evaluated expression `d[...]`.
pyget() { python3 -c "import json,sys;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# ---- preflight -------------------------------------------------------------
echo "== preflight =="
if ! curl -s --max-time 15 "$ORCH/health" | pyget "d['status']" | grep -q healthy; then
  echo "ERROR: orchestration not healthy at $ORCH"; exit 1
fi
if ! curl -sI --max-time 6 "$FILE_URL" | head -1 | grep -q 200; then
  log_issue "download server $FILE_URL not returning 200 before run"
fi
echo "  stack healthy; server reachable"

# ---- one run ---------------------------------------------------------------
# args: CC BW RTT
run_one() {
  local CC=$1 BW=$2 RTT=$3
  local TAG="${CC}_${BW}bw-${RTT}rtt-${Q}q"
  echo ""
  echo "========================================================"
  echo "  RUN: $TAG   (${DUR}s, 1 trial)"
  echo "========================================================"

  # 1) set host CC (the sender)
  echo "-- setting host tcp_congestion_control=$CC"
  if ! sysctl -w net.ipv4.tcp_congestion_control="$CC" >/dev/null 2>&1; then
    log_issue "$TAG: sysctl -w tcp_congestion_control=$CC FAILED (skipping run)"; return 1
  fi
  local GOT; GOT=$(cat /proc/sys/net/ipv4/tcp_congestion_control)
  if [ "$GOT" != "$CC" ]; then
    log_issue "$TAG: host CC is '$GOT' after set, expected '$CC' (skipping run)"; return 1
  fi
  echo "   host CC now: $GOT"

  # 2) submit intent
  local INTENT="Run a wget download from $FILE_URL over a ${BW} Mbps bottleneck with ${RTT} ms added latency, pfifo queue of ${Q} packets and ${CC} congestion control. Do not store the downloaded file (write it to /dev/null). Stop the wget process after ${DUR} seconds. One trial."
  local PAYLOAD
  PAYLOAD=$(python3 - "$INTENT" "$BW" "$RTT" "$CC" "$Q" "$DUR" <<'PY'
import json,sys
intent,bw,rtt,cc,q,dur=sys.argv[1:7]
print(json.dumps({
  "intent": intent,
  # Pin the wget workflow by id -> bypasses the flaky LLM library picker, which
  # otherwise rejects it for "not configuring shaping" (shaping is the worker's
  # job, applied deterministically from context below, not the workflow's).
  "workflow_id": "test_wget_workflow",
  "context": {
    "capacities":[int(bw)],"latencies":[int(rtt)],"cc_algorithms":[cc],
    "aqm_policy":"pfifo","buffer_packets":int(q),"qdisc_params":{},
    "duration_seconds":int(dur),"num_trials":1,
  },
}))
PY
)
  local T_SUBMIT; T_SUBMIT=$(date +%s.%N)
  local ORCH_ID; ORCH_ID=$(curl -s -X POST "$ORCH/intent" -H 'Content-Type: application/json' \
      -d "$PAYLOAD" | pyget "d['orchestration_id']")
  if [ -z "${ORCH_ID:-}" ]; then
    log_issue "$TAG: intent submission returned no orchestration_id"; return 1
  fi
  echo "-- submitted; orch_id=$ORCH_ID"

  # 3) poll to completion (max ~360s: whole-minute-boundary wait + 60s run + overhead)
  local STATUS deadline; deadline=$(( $(date +%s) + 360 ))
  while :; do
    STATUS=$(curl -s "$ORCH/orchestration/$ORCH_ID" | pyget "d['status']")
    [ "$STATUS" = complete ] && break
    [ "$STATUS" = failed ] && break
    if [ "$(date +%s)" -gt "$deadline" ]; then STATUS="timeout"; break; fi
    printf "   %s status=%s\r" "$(date +%T)" "$STATUS"; sleep 5
  done
  local T_FINISH; T_FINISH=$(date +%s.%N)
  local WALL; WALL=$(echo "$T_FINISH - $T_SUBMIT" | bc)
  echo ""
  echo "-- final status=$STATUS  wall=${WALL}s"
  [ "$STATUS" != complete ] && log_issue "$TAG: orchestration ended status=$STATUS (orch=$ORCH_ID)"

  # 4) resolve experiment_id -> telemetry result_id
  local EXP RID
  EXP=$(curl -s "$ORCH/orchestration/$ORCH_ID/results" | pyget "d['results'][0]['experiment_id']")
  if [ -z "${EXP:-}" ]; then
    log_issue "$TAG: no experiment_id from orchestration results (orch=$ORCH_ID)"
    echo ",${CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"
    return 1
  fi
  echo "-- experiment_id=$EXP"
  RID=$(curl -s "$TELE/results?experiment_id=$EXP&limit=1" | pyget "d['results'][0]['result_id']")

  # 5) download artifacts (pcap + queue_trace) + full result json
  if [ -n "${RID:-}" ]; then
    echo "-- result_id=$RID; downloading artifacts"
    curl -s "$TELE/results/$RID" -o "$RESULTS/${TAG}__result.json"
    # iterate artifacts: emit "artifact_id<TAB>artifact_type<TAB>filename"
    curl -s "$TELE/results/$RID/artifacts" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d.get('artifacts',[]):
    print('\t'.join([str(a.get('artifact_id','')),str(a.get('artifact_type','')),str(a.get('filename',''))]))
" | while IFS=$'\t' read -r AID ATYPE FN; do
      [ -z "$AID" ] && continue
      local OUT="$RESULTS/${TAG}__${ATYPE}__${FN}"
      curl -s "$TELE/artifacts/$AID" -o "$OUT"
      echo "     saved $(basename "$OUT") ($(wc -c <"$OUT") bytes)"
    done
  else
    log_issue "$TAG: telemetry has no result row for experiment_id=$EXP"
  fi

  # 6) timing row
  echo "${EXP},${CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"
  echo "-- timing row appended"
}

# Optional CLI args select which CCs to run (e.g. `... run_cc_queue.sh cubic bbr`).
# No args -> all three. Lets you re-run just the ones that failed.
SELECTED=("$@")
maybe() { SEL_CC=$1; if [ ${#SELECTED[@]} -eq 0 ] || printf '%s\n' "${SELECTED[@]}" | grep -qx "$1"; then run_one "$@"; else echo "-- skipping $1 (not selected)"; fi; }

maybe cubic 10 85
maybe bbr   10 275
maybe reno  15 139

# restore a sane default CC
sysctl -w net.ipv4.tcp_congestion_control=cubic >/dev/null 2>&1 || true

echo ""
echo "== DONE =="
echo "  artifacts + timing in: $RESULTS"
column -t -s, "$TIMING" 2>/dev/null || cat "$TIMING"
