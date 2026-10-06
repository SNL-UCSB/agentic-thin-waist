#!/usr/bin/env bash
# run_cc_fig5_nooffload.sh — re-collect Figure 5 (Cubic, 5 Mbps, 275 ms,
# pfifo 32/128/512/1024) with packet merging OFF and large TCP buffers, so the
# bottleneck queue holds real MTU-sized packets like the paper's BESS switch.
#
# Why: the July runs queued ~2896 B skbs (2 x MSS: TSO autosizing floor of
# tcp_min_tso_segs=2 on the sender), so "Nq" really held ~2N packets, and the
# client rwnd capped at 3.15 MB (tcp_rmem max 6 MB / 2), which limited 1024q.
#
# Changes applied for the duration of the run (all restored on exit):
#   sender (this host):  tcp_min_tso_segs=1, tcp_wmem max 32 MB,
#                        tso/gso/gro off on the docker bridge + substrate veth
#   substrate-worker:    tso/gso/gro off on every iface in the container root
#                        netns, ns1 and ns2
#   client (ns1):        tcp_rmem max 32 MB (rwnd up to ~16 MB)
#
# Workload is unchanged: wget http://128.111.5.237:8888/1GB.bin -> /dev/null, 60 s.
# Artifacts land in cc_results/ tagged  cubic_5bw-275rtt-<Q>q-nooffload__*
# (the July files stay untouched). Offload/sysctl state is logged to
# cc_results/fig5_nooffload_settings.txt.
#
# ROOT REQUIRED (sysctl, ethtool, nsenter, docker). Run with:
#     sudo bash /home/jaber/agentic-thin-waist/run_cc_fig5_nooffload.sh
#
# RESUMABLE: skips any run whose __result.json already exists.

set -uo pipefail

REPO=/home/jaber/agentic-thin-waist
RESULTS="$REPO/cc_results"
REPORT="$REPO/cc_report.md"
ORCH=http://localhost:8005
TELE=http://localhost:8004
FILE_URL=http://128.111.5.237:8888/1GB.bin
DUR=60
SUFFIX=nooffload
CTR=substrate-worker
BIG=33554432   # 32 MB
SETTINGS_LOG="$RESULTS/fig5_${SUFFIX}_settings.txt"
STATE=$(mktemp)  # original offload states, for restore

SETTINGS=(
  "cubic 5 275 32"
  "cubic 5 275 128"
  "cubic 5 275 512"
  "cubic 5 275 1024"
)

[ "$(id -u)" = 0 ] || { echo "ERROR: run with sudo"; exit 1; }
command -v ethtool >/dev/null || { echo "ERROR: ethtool not found on host"; exit 1; }

mkdir -p "$RESULTS"
TIMING="$RESULTS/timing.csv"
[ -f "$TIMING" ] || echo "experiment_id,cc,bw_mbps,rtt_ms,queue_pkts,declared_duration_s,t_submit_epoch,t_finish_epoch,wall_s,status" > "$TIMING"

log_issue() { echo "$(date -Iseconds) | $1" >> "$REPORT"; echo "  [issue] $1"; }
pyget()     { python3 -c "import json,sys;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

# ---- namespace helpers -----------------------------------------------------
PID=$(docker inspect -f '{{.State.Pid}}' "$CTR" 2>/dev/null)
[ -n "${PID:-}" ] && [ "$PID" != 0 ] || { echo "ERROR: $CTR not running"; exit 1; }

# in_ns <host|ctr|ns1|ns2> cmd...   (uses the HOST's ethtool/sysctl binaries)
in_ns() {
  local ns=$1; shift
  case $ns in
    host) "$@" ;;
    ctr)  nsenter --net="/proc/$PID/ns/net" "$@" ;;
    *)    nsenter --net="/proc/$PID/root/run/netns/$ns" "$@" ;;
  esac
}
ifaces_in() { in_ns "$1" ip -o link show | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -v '^lo$'; }

feat() {  # feat <ns> <iface> <ethtool -k label> -> on|off
  in_ns "$1" ethtool -k "$2" 2>/dev/null | awk -v k="$3:" '$1==k{print $2; exit}'
}

offload_off() {  # offload_off <ns> <iface>: remember state, then turn off
  local ns=$1 i=$2
  echo "$ns $i $(feat "$ns" "$i" tcp-segmentation-offload) $(feat "$ns" "$i" generic-segmentation-offload) $(feat "$ns" "$i" generic-receive-offload)" >> "$STATE"
  in_ns "$ns" ethtool -K "$i" tso off gso off gro off 2>/dev/null \
    || in_ns "$ns" ethtool -K "$i" gso off gro off 2>/dev/null || true
}

# ---- save originals + restore trap ----------------------------------------
ORIG_CC=$(sysctl -n net.ipv4.tcp_congestion_control)
ORIG_MINTSO=$(sysctl -n net.ipv4.tcp_min_tso_segs)
ORIG_WMEM=$(sysctl -n net.ipv4.tcp_wmem)
ORIG_RMEM_NS1=$(in_ns ns1 sysctl -n net.ipv4.tcp_rmem) \
  || { echo "ERROR: cannot enter ns1 via /proc/$PID/root/run/netns/ns1"; exit 1; }

restore() {
  echo ""; echo "== restoring host/worker settings =="
  sysctl -qw net.ipv4.tcp_congestion_control="$ORIG_CC"
  sysctl -qw net.ipv4.tcp_min_tso_segs="$ORIG_MINTSO"
  sysctl -qw net.ipv4.tcp_wmem="$ORIG_WMEM"
  in_ns ns1 sysctl -qw net.ipv4.tcp_rmem="$ORIG_RMEM_NS1" 2>/dev/null || true
  while read -r ns i tso gso gro; do
    [ -n "$tso" ] && in_ns "$ns" ethtool -K "$i" tso "$tso" 2>/dev/null
    [ -n "$gso" ] && in_ns "$ns" ethtool -K "$i" gso "$gso" 2>/dev/null
    [ -n "$gro" ] && in_ns "$ns" ethtool -K "$i" gro "$gro" 2>/dev/null
  done < "$STATE"
  rm -f "$STATE"
  echo "  restored CC=$ORIG_CC min_tso_segs=$ORIG_MINTSO wmem='$ORIG_WMEM' ns1 rmem='$ORIG_RMEM_NS1' + offloads"
}
trap restore EXIT

# ---- preflight -------------------------------------------------------------
echo "== preflight =="
curl -s --max-time 15 "$ORCH/health" | pyget "d['status']" | grep -q healthy \
  || { echo "ERROR: orchestration not healthy at $ORCH"; exit 1; }
curl -sI --max-time 6 "$FILE_URL" | head -1 | grep -q 200 \
  || log_issue "download server $FILE_URL not returning 200 at start"

# ---- apply: no packet merging + big buffers --------------------------------
echo "== disabling packet merging (TSO/GSO/GRO) =="
# host side: substrate container's veth peer and the docker bridge it sits on
CIDX=$(in_ns ctr cat /sys/class/net/eth0/iflink)
HVETH=$(ip -o link | awk -F': ' -v n="$CIDX" '$1==n{print $2}' | cut -d@ -f1)
HBR=$(ip -o link show "$HVETH" | grep -o 'master [^ ]*' | awk '{print $2}')
echo "  host: veth=$HVETH bridge=$HBR"
for i in $HVETH $HBR; do offload_off host "$i"; done
for ns in ctr ns1 ns2; do
  for i in $(ifaces_in "$ns"); do offload_off "$ns" "$i"; done
done

echo "== TCP buffers / TSO sizing =="
sysctl -qw net.ipv4.tcp_min_tso_segs=1
sysctl -qw net.ipv4.tcp_wmem="4096 16384 $BIG"
in_ns ns1 sysctl -qw net.ipv4.tcp_rmem="4096 131072 $BIG"

# provenance
{
  echo "# Figure 5 no-offload campaign — $(date -Iseconds)"
  echo "host: tcp_min_tso_segs=$(sysctl -n net.ipv4.tcp_min_tso_segs) tcp_wmem='$(sysctl -n net.ipv4.tcp_wmem)'"
  echo "ns1:  tcp_rmem='$(in_ns ns1 sysctl -n net.ipv4.tcp_rmem)' tcp_adv_win_scale=$(in_ns ns1 sysctl -n net.ipv4.tcp_adv_win_scale)"
  for ns in host ctr ns1 ns2; do
    if [ $ns = host ]; then L="$HVETH $HBR"; else L=$(ifaces_in $ns); fi
    for i in $L; do
      echo "$ns/$i: tso=$(feat $ns $i tcp-segmentation-offload) gso=$(feat $ns $i generic-segmentation-offload) gro=$(feat $ns $i generic-receive-offload)"
    done
  done
} | tee "$SETTINGS_LOG"

# ---- one run: CC BW RTT Q --------------------------------------------------
run_one() {
  local CC=$1 BW=$2 RTT=$3 Q=$4
  local TAG="${CC}_${BW}bw-${RTT}rtt-${Q}q-${SUFFIX}"

  if [ -s "$RESULTS/${TAG}__result.json" ]; then
    echo "-- skip $TAG (already collected)"; return 0
  fi
  echo ""
  echo "===== [$RUN_IDX/$RUN_TOTAL] $TAG  (${DUR}s, kernel cc=$CC) ====="

  if ! sysctl -w net.ipv4.tcp_congestion_control="$CC" >/dev/null 2>&1 \
       || [ "$(cat /proc/sys/net/ipv4/tcp_congestion_control)" != "$CC" ]; then
    log_issue "$TAG: could not set host CC to '$CC' (skipping)"; return 1
  fi

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

  local EXP RID
  EXP=$(curl -s "$ORCH/orchestration/$ORCH_ID/results" | pyget "d['results'][0]['experiment_id']")
  if [ -z "${EXP:-}" ]; then
    log_issue "$TAG: no experiment_id (orch=$ORCH_ID)"
    echo ",${CC}-${SUFFIX},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"; return 1
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

  # sanity: queued bytes per packet should now be ~1500, not ~2900
  local QT; QT=$(ls "$RESULTS/${TAG}"__queue_trace__* 2>/dev/null | head -1)
  if [ -n "$QT" ]; then
    python3 - "$QT" "$Q" <<'PY'
import json,sys
b=p=mx=0
for line in open(sys.argv[1]):
    r=json.loads(line)
    if r.get('iface')!='veth2' or not r.get('backlog_pkts'): continue
    b+=r['backlog_bytes']; p+=r['backlog_pkts']; mx=max(mx,r['backlog_pkts'])
bpp=b/p if p else 0
print(f"-- check: veth2 bytes/queued pkt = {bpp:.0f}  (max backlog {mx}/{sys.argv[2]} pkts)"
      + ("   <-- STILL MERGED" if bpp>1600 else "   OK (MTU-sized)"))
PY
  fi

  echo "${EXP},${CC}-${SUFFIX},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" >> "$TIMING"
}

RUN_TOTAL=${#SETTINGS[@]}
RUN_IDX=0
for entry in "${SETTINGS[@]}"; do
  RUN_IDX=$((RUN_IDX+1))
  # shellcheck disable=SC2086
  run_one $entry
done

echo ""
echo "== COLLECTION DONE =="
ls -la "$RESULTS"/cubic_5bw-275rtt-*q-${SUFFIX}__queue_trace__* 2>/dev/null || echo "   (none)"
echo "Now run the last cells of cc_fig5_paperstyle.ipynb."
