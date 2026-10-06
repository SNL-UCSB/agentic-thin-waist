#!/usr/bin/env bash
# Collect ONE Exp6 TESTING cell: wget download of a large file over a single
# shaped mahimahi bottleneck, sender CCA pinned via the cc_server origin
# (setsockopt TCP_CONGESTION). Self-consistent with the iperf training cells
# (same emulator). No root (mahimahi setuid; origin is unprivileged).
#
# Usage: run_wget_cell.sh <bw> <rtt> <queue> <cca> <rep> <secs> <port> [outroot]
set -u
BW=$1; RTT=$2; QP=$3; CCA=$4; REP=$5; SECS=$6; PORT=$7
OUTROOT="${8:-/home/jaber/agentic-thin-waist/cc_classifier/phase2/test}"
OWD=$(( RTT / 2 ))
ROOT=/home/jaber/agentic-thin-waist
AIH=$ROOT/ai_cc/harness
SETTING="${BW}bw-${RTT}rtt-${QP}q"
RUNDIR="$OUTROOT/$SETTING/$CCA/$REP"
mkdir -p "$RUNDIR"
TRACE="$AIH/${BW}mbit.trace"
[ -f "$TRACE" ] || python3 "$AIH/gen_trace.py" "$BW" 12000 > "$TRACE"
DOWNLOG="$RUNDIR/down.log"
OCC="$RUNDIR/test_occupancy.csv"

# 1) start a fresh CCA-pinned origin (sender CCA inherited by accepted sockets)
python3 "$AIH/cc_server.py" "$ROOT/ai_cc/srv" "$PORT" "$CCA" >/tmp/origin_${PORT}.log 2>&1 &
SRV=$!
sleep 0.6
kill -0 $SRV 2>/dev/null || { echo "[cell] origin failed cca=$CCA"; cat /tmp/origin_${PORT}.log; exit 2; }

# 2) wget through the shaped downlink; occupancy from mm-link downlink log
T0=$(date +%s.%N)
INNERSH="$RUNDIR/inner.sh"
cat > "$INNERSH" <<INNEREOF
set -u
timeout $SECS wget -O /dev/null --header="Cache-Control: no-cache" \
  "http://\$MAHIMAHI_BASE:$PORT/bigfile.bin" 2>/dev/null
true
INNEREOF

mm-delay "$OWD" mm-link "$TRACE" "$TRACE" \
  --downlink-queue=droptail --downlink-queue-args="packets=$QP" \
  --downlink-log="$DOWNLOG" -- bash "$INNERSH"
T1=$(date +%s.%N)
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null

python3 "$AIH/queue_occupancy.py" "$DOWNLOG" 20 > "$OCC" 2>/dev/null
DELIV=$(awk '$2=="-"{s+=$3} END{print s+0}' "$DOWNLOG" 2>/dev/null)
DROPS=$(awk '$2=="d"{n++} END{print n+0}' "$DOWNLOG" 2>/dev/null)
NROWS=$(( $(wc -l < "$OCC" 2>/dev/null) - 1 ))
ELAPSED=$(awk "BEGIN{printf \"%.1f\", $T1-$T0}")
cat > "$RUNDIR/metadata.json" <<META
{"setting":"$SETTING","bandwidth_mbps":$BW,"base_rtt_ms":$RTT,"queue_pkts":$QP,
 "cca":"$CCA","workload":"wget","role":"testing","rep":$REP,
 "duration_s_target":$SECS,"duration_s_actual":$ELAPSED,
 "bytes_delivered":$DELIV,"drops":$DROPS,"occupancy_rows":$NROWS}
META
echo "[cell] TEST $SETTING/$CCA/rep$REP deliv=${DELIV}B drops=${DROPS} occ_rows=${NROWS} (${ELAPSED}s)"
