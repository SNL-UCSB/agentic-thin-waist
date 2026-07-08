#!/usr/bin/env bash
# run_cc_campaign.sh — full CCAnalyzer Exp6 replication sweep on the local stack.
#
#   Main collection : 9 coupled <bw-rtt-queue> settings × 15 CCs   (135 runs)
#   Queue sweep     : 5 Mbps / 275 ms, queue ∈ {32,128,512,1024} × 15 CCs (60 runs)
#   (5/275/128 overlaps the main grid → deduped by resume-skip → ~180 distinct runs)
#
# Every run: 60 s, 1 trial, wget of http://128.111.5.237:8888/1GB.bin -> /dev/null,
# pfifo queue. For each run it sets the HOST congestion control (this host is the
# file server = the sender), submits the intent (workflow pinned, no LLM picker),
# polls to completion, downloads pcap + queue_trace + result.json into cc_results/,
# and appends a timing row.
#
# Sequential BY DESIGN: the host CC is a single global knob, so runs must not
# overlap (see cc.md §0). Expect ~2–3 min/run ⇒ ~7–8 h total.
#
# ROOT REQUIRED (sysctl + modprobe). Run detached so it survives your shell:
#     sudo nohup bash /home/jaber/agentic-thin-waist/run_cc_campaign.sh \
#          > /home/jaber/agentic-thin-waist/cc_results/campaign.log 2>&1 &
#     tail -f /home/jaber/agentic-thin-waist/cc_results/campaign.log
#
# RESUMABLE: re-running skips any run whose result.json already exists, so a
# ctrl-C / crash / power blip just picks up where it left off.
#
# SELECT A SUBSET (optional):
#     ENV toggles:  RUN_MAIN=1 RUN_QSWEEP=1   (set either to 0 to skip that block)
#     CC filter:    pass CC names as args  ->  `... run_cc_campaign.sh cubic bbr reno`
#
# No jq dependency (python3 for JSON).

set -uo pipefail

REPO=/home/jaber/agentic-thin-waist
RESULTS="$REPO/cc_results"
REPORT="$REPO/cc_report.md"
ORCH=http://localhost:8005
TELE=http://localhost:8004
FILE_URL=http://128.111.5.237:8888/1GB.bin
DUR=60
RUN_MAIN=${RUN_MAIN:-1}
RUN_QSWEEP=${RUN_QSWEEP:-1}

# The 15 built-in wide-area Linux CCAs (paper NewReno=reno, New Vegas=nv).
ALL_CCS=(reno cubic bbr bic cdg highspeed htcp hybla illinois nv scalable vegas veno westwood yeah)

# 9 coupled settings "bw rtt queue" (queue ≈ 1 BDP).
SETTINGS_MAIN=(
  "5 85 64"  "5 130 64"  "5 275 128"
  "10 85 128" "10 130 128" "10 275 256"
  "15 85 256" "15 130 256" "15 275 512"
)
# Queue-size sweep at fixed 5 Mbps / 275 ms.
SETTINGS_QSWEEP=(
  "5 275 32" "5 275 128" "5 275 512" "5 275 1024"
)

mkdir -p "$RESULTS"
TIMING="$RESULTS/timing.csv"
[ -f "$TIMING" ] || echo "experiment_id,cc,bw_mbps,rtt_ms,queue_pkts,declared_duration_s,t_submit_epoch,t_finish_epoch,wall_s,status" > "$TIMING"

log_issue() { echo "$(date -Iseconds) | $1" >> "$REPORT"; echo "  [issue] $1"; }
pyget()     { python3 -c "import json,sys;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# ---- CC selection (args filter) --------------------------------------------
CCS=()
if [ "$#" -gt 0 ]; then
  for c in "${ALL_CCS[@]}"; do for a in "$@"; do [ "$c" = "$a" ] && CCS+=("$c"); done; done
else
  CCS=("${ALL_CCS[@]}")
fi

# ---- preflight -------------------------------------------------------------
echo "== preflight =="
curl -s --max-time 15 "$ORCH/health" | pyget "d['status']" | grep -q healthy \
  || { echo "ERROR: orchestration not healthy at $ORCH"; exit 1; }
curl -sI --max-time 6 "$FILE_URL" | head -1 | grep -q 200 \
  || log_issue "download server $FILE_URL not returning 200 at start"

# Load every CC module, then keep only the ones the kernel actually exposes.
for c in "${CCS[@]}"; do modprobe "tcp_$c" 2>/dev/null || true; done
AVAIL=" $(cat /proc/sys/net/ipv4/tcp_available_congestion_control) "
USABLE=()
for c in "${CCS[@]}"; do
  if [[ "$AVAIL" == *" $c "* ]]; then USABLE+=("$c"); else log_issue "CC '$c' not available on host — dropped from campaign"; fi
done
CCS=("${USABLE[@]}")
echo "  stack healthy; ${#CCS[@]} usable CCs: ${CCS[*]}"

# ---- one run: CC BW RTT Q --------------------------------------------------
run_one() {
  local CC=$1 BW=$2 RTT=$3 Q=$4
  local TAG="${CC}_${BW}bw-${RTT}rtt-${Q}q"

  # resume-skip: already collected?
  if [ -s "$RESULTS/${TAG}__result.json" ]; then
    echo "-- skip $TAG (already collected)"; return 0
  fi

  echo ""
  echo "===== [$RUN_IDX/$RUN_TOTAL] $TAG  (${DUR}s) ====="

  # 1) host CC (sender)
  if ! sysctl -w net.ipv4.tcp_congestion_control="$CC" >/dev/null 2>&1 \
       || [ "$(cat /proc/sys/net/ipv4/tcp_congestion_control)" != "$CC" ]; then
    log_issue "$TAG: could not set host CC to '$CC' (skipping)"; return 1
  fi

  # 2) submit (workflow pinned -> deterministic, bypasses flaky library picker)
  local INTENT="Run a wget download from $FILE_URL over a ${BW} Mbps bottleneck with ${RTT} ms added latency, pfifo queue of ${Q} packets and ${CC} congestion control. Do not store the downloaded file (write it to /dev/null). Stop the wget process after ${DUR} seconds. One trial."
  local PAYLOAD
  PAYLOAD=$(python3 - "$INTENT" "$BW" "$RTT" "$CC" "$Q" "$DUR" <<'PY'
import json,sys
intent,bw,rtt,cc,q,dur=sys.argv[1:7]
print(json.dumps({
  "intent": intent,
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
  local ORCH_ID; ORCH_ID=$(curl -s -X POST "$ORCH/intent" -H 'Content-Type: application/json' -d "$PAYLOAD" | pyget "d['orchestration_id']")
  [ -z "${ORCH_ID:-}" ] && { log_issue "$TAG: no orchestration_id from submit"; return 1; }
  echo "-- orch=$ORCH_ID"

  # 3) poll to completion
  local STATUS deadline; deadline=$(( $(date +%s) + 360 ))
  while :; do
    STATUS=$(curl -s "$ORCH/orchestration/$ORCH_ID" | pyget "d['status']")
    [ "$STATUS" = complete ] && break
    [ "$STATUS" = failed ] && break
    [ "$(date +%s)" -gt "$deadline" ] && { STATUS=timeout; break; }
    sleep 5
  done
  local T_FINISH; T_FINISH=$(date +%s.%N)
  local WALL; WALL=$(echo "$T_FINISH - $T_SUBMIT" | bc)
  echo "-- status=$STATUS wall=${WALL}s"
  [ "$STATUS" != complete ] && log_issue "$TAG: orchestration status=$STATUS (orch=$ORCH_ID)"

  # 4) experiment_id -> result_id -> artifacts
  local EXP RID
  EXP=$(curl -s "$ORCH/orchestration/$ORCH_ID/results" | pyget "d['results'][0]['experiment_id']")
  if [ -z "${EXP:-}" ]; then
    log_issue "$TAG: no experiment_id (orch=$ORCH_ID)"
    echo ",${CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"; return 1
  fi
  RID=$(curl -s "$TELE/results?experiment_id=$EXP&limit=1" | pyget "d['results'][0]['result_id']")
  if [ -n "${RID:-}" ]; then
    curl -s "$TELE/results/$RID" -o "$RESULTS/${TAG}__result.json"
    curl -s "$TELE/results/$RID/artifacts" | python3 -c "
import json,sys
for a in json.load(sys.stdin).get('artifacts',[]):
    print('\t'.join([str(a.get('artifact_id','')),str(a.get('artifact_type','')),str(a.get('filename',''))]))
" | while IFS=$'\t' read -r AID ATYPE FN; do
      [ -z "$AID" ] && continue
      curl -s "$TELE/artifacts/$AID" -o "$RESULTS/${TAG}__${ATYPE}__${FN}"
    done
    echo "-- collected artifacts for $EXP"
  else
    log_issue "$TAG: telemetry has no result for $EXP"
  fi

  echo "${EXP},${CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"
}

# ---- build the ordered run list (setting-major, CC-minor) ------------------
RUN_LIST=()
add_block() { local -n arr=$1; for s in "${arr[@]}"; do for c in "${CCS[@]}"; do RUN_LIST+=("$c $s"); done; done; }
[ "$RUN_MAIN"   = 1 ] && add_block SETTINGS_MAIN
[ "$RUN_QSWEEP" = 1 ] && add_block SETTINGS_QSWEEP
RUN_TOTAL=${#RUN_LIST[@]}
echo "== campaign: $RUN_TOTAL run slots (resume-skip removes already-collected) =="

# ---- execute ---------------------------------------------------------------
RUN_IDX=0
for entry in "${RUN_LIST[@]}"; do
  RUN_IDX=$((RUN_IDX+1))
  # shellcheck disable=SC2086
  run_one $entry
done

# restore a sane default
sysctl -w net.ipv4.tcp_congestion_control=cubic >/dev/null 2>&1 || true

echo ""
echo "== CAMPAIGN DONE =="
COMPLETE=$(grep -c ',complete$' "$TIMING" 2>/dev/null || echo 0)
echo "  complete rows in timing.csv: $COMPLETE"
echo "  artifacts + timing in: $RESULTS"
