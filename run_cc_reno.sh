#!/usr/bin/env bash
# run_cc_reno.sh — fresh **Reno** + 4-CCA collection for cc_queue.ipynb.
#
# Context: the July campaign's `reno_*` artifacts stay on disk and keep their
# paper label **NewReno**. Fresh Reno runs are collected under the tag prefix
# `reno2_` and labeled **Reno** in the notebook.
#
# BLOCK A — new 20 ms setting (10 Mbps, 128-pkt pfifo, 20 ms added latency):
#     reno2, cubic, bbr, bic        -> §7 "new block" in cc_queue.ipynb
#   All four CCAs collected fresh so the panel is internally consistent.
#
# BLOCK B — Reno at the original Figure-1 setting (10 Mbps, 130 ms, 128 pkt):
#     reno2                         -> lets Figure 1 regenerate with the Reno
#   label instead of NewReno. Its Cubic/BBR/BIC panels reuse the July artifacts,
#   which already exist. Skip with RUN_FIG1_RENO=0.
#
# All runs: 60 s, 1 trial, wget of http://128.111.5.237:8888/1GB.bin -> /dev/null.
# Sets the HOST congestion control (this host is the file server = the sender),
# submits the intent with the wget workflow pinned, polls to completion, and
# downloads pcap + queue_trace + result.json into cc_results/.
#
# ROOT REQUIRED (sysctl). Run with:
#     sudo bash /home/jaber/agentic-thin-waist/run_cc_reno.sh
#
# RESUMABLE: skips any run whose __result.json already exists.
# Sequential BY DESIGN: host CC is a single global knob, runs must not overlap.

set -uo pipefail

REPO=/home/jaber/agentic-thin-waist
RESULTS="$REPO/cc_results"
REPORT="$REPO/cc_report.md"
ORCH=http://localhost:8005
TELE=http://localhost:8004
FILE_URL=http://128.111.5.237:8888/1GB.bin
DUR=60
RUN_FIG1_RENO=${RUN_FIG1_RENO:-1}

# Fresh-Reno artifacts are tagged `reno2_` so they never collide with the July
# `reno_` (NewReno) set. Kernel CCA is plain `reno` for both.
TAG_OF_CC() { [ "$1" = reno ] && echo reno2 || echo "$1"; }

# BLOCK A: "cc bw rtt queue" — the new 20 ms four-CCA panel.
SETTINGS_NEW=(
  "reno  10 20 128"
  "cubic 10 20 128"
  "bbr   10 20 128"
  "bic   10 20 128"
)
# BLOCK B: Reno at the original Figure-1 setting.
SETTINGS_FIG1=(
  "reno  10 130 128"
)

mkdir -p "$RESULTS"
TIMING="$RESULTS/timing.csv"
[ -f "$TIMING" ] || echo "experiment_id,cc,bw_mbps,rtt_ms,queue_pkts,declared_duration_s,t_submit_epoch,t_finish_epoch,wall_s,status" > "$TIMING"

log_issue() { echo "$(date -Iseconds) | $1" >> "$REPORT"; echo "  [issue] $1"; }
pyget()     { python3 -c "import json,sys;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# ---- preflight -------------------------------------------------------------
echo "== preflight =="
curl -s --max-time 15 "$ORCH/health" | pyget "d['status']" | grep -q healthy \
  || { echo "ERROR: orchestration not healthy at $ORCH"; exit 1; }
curl -sI --max-time 6 "$FILE_URL" | head -1 | grep -q 200 \
  || log_issue "download server $FILE_URL not returning 200 at start"
for c in reno cubic bbr bic; do
  modprobe "tcp_$c" 2>/dev/null || true
  grep -qw "$c" /proc/sys/net/ipv4/tcp_available_congestion_control \
    || { echo "ERROR: CC '$c' not available on host"; exit 1; }
done
echo "  stack healthy; server reachable; reno/cubic/bbr/bic all available"
echo "  host CC currently '$(cat /proc/sys/net/ipv4/tcp_congestion_control)'"

# ---- one run: CC BW RTT Q --------------------------------------------------
run_one() {
  local CC=$1 BW=$2 RTT=$3 Q=$4
  local TAG_CC; TAG_CC=$(TAG_OF_CC "$CC")
  local TAG="${TAG_CC}_${BW}bw-${RTT}rtt-${Q}q"

  if [ -s "$RESULTS/${TAG}__result.json" ]; then
    echo "-- skip $TAG (already collected)"; return 0
  fi

  echo ""
  echo "===== [$RUN_IDX/$RUN_TOTAL] $TAG  (${DUR}s, kernel cc=$CC) ====="

  # 1) host CC (sender)
  if ! sysctl -w net.ipv4.tcp_congestion_control="$CC" >/dev/null 2>&1 \
       || [ "$(cat /proc/sys/net/ipv4/tcp_congestion_control)" != "$CC" ]; then
    log_issue "$TAG: could not set host CC to '$CC' (skipping)"; return 1
  fi
  echo "-- host CC now: $(cat /proc/sys/net/ipv4/tcp_congestion_control)"

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
    printf "   %s status=%s\r" "$(date +%T)" "$STATUS"; sleep 5
  done
  local T_FINISH; T_FINISH=$(date +%s.%N)
  local WALL; WALL=$(echo "$T_FINISH - $T_SUBMIT" | bc)
  echo ""
  echo "-- status=$STATUS wall=${WALL}s"
  [ "$STATUS" != complete ] && log_issue "$TAG: orchestration status=$STATUS (orch=$ORCH_ID)"

  # 4) experiment_id -> result_id -> artifacts
  local EXP RID
  EXP=$(curl -s "$ORCH/orchestration/$ORCH_ID/results" | pyget "d['results'][0]['experiment_id']")
  if [ -z "${EXP:-}" ]; then
    log_issue "$TAG: no experiment_id (orch=$ORCH_ID)"
    echo ",${TAG_CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"; return 1
  fi
  echo "-- experiment_id=$EXP"
  RID=$(curl -s "$TELE/results?experiment_id=$EXP&limit=1" | pyget "d['results'][0]['result_id']")
  if [ -n "${RID:-}" ]; then
    curl -s "$TELE/results/$RID" -o "$RESULTS/${TAG}__result.json"
    curl -s "$TELE/results/$RID/artifacts" | python3 -c "
import json,sys
for a in json.load(sys.stdin).get('artifacts',[]):
    print('\t'.join([str(a.get('artifact_id','')),str(a.get('artifact_type','')),str(a.get('filename',''))]))
" | while IFS=$'\t' read -r AID ATYPE FN; do
      [ -z "$AID" ] && continue
      OUT="$RESULTS/${TAG}__${ATYPE}__${FN}"
      curl -s "$TELE/artifacts/$AID" -o "$OUT"
      echo "     saved $(basename "$OUT") ($(wc -c <"$OUT") bytes)"
    done
  else
    log_issue "$TAG: telemetry has no result for $EXP"
  fi

  # 5) timing row — cc column carries the TAG prefix (reno2, not reno) so the
  #    fresh Reno series is distinguishable from the July NewReno rows.
  echo "${EXP},${TAG_CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"
}

# ---- build run list --------------------------------------------------------
RUN_LIST=("${SETTINGS_NEW[@]}")
[ "$RUN_FIG1_RENO" = 1 ] && RUN_LIST+=("${SETTINGS_FIG1[@]}")
RUN_TOTAL=${#RUN_LIST[@]}
echo "== $RUN_TOTAL run slots (resume-skip removes already-collected) =="

RUN_IDX=0
for entry in "${RUN_LIST[@]}"; do
  RUN_IDX=$((RUN_IDX+1))
  # shellcheck disable=SC2086
  run_one $entry
done

# restore a sane default CC
sysctl -w net.ipv4.tcp_congestion_control=cubic >/dev/null 2>&1 || true

echo ""
echo "== COLLECTION DONE =="
echo "-- 20 ms four-CCA set:"
ls -la "$RESULTS"/{reno2,cubic,bbr,bic}_10bw-20rtt-128q__queue_trace__* 2>/dev/null || echo "   (none)"
echo "-- Figure-1 Reno:"
ls -la "$RESULTS"/reno2_10bw-130rtt-128q__queue_trace__* 2>/dev/null || echo "   (none)"
