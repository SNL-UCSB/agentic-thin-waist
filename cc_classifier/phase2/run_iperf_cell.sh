#!/usr/bin/env bash
# Collect ONE Exp6 TRAINING cell: an iperf flow over a single shaped mahimahi
# bottleneck under a chosen sender CCA, recording the bottleneck queue-occupancy
# trace from mm-link's downlink log. Mirrors ai_cc/harness/run_cell.sh (wget) but
# uses iperf3 in reverse mode (server -> client), matching the paper's iperf
# training workload. No root: mahimahi is setuid; CCA set via scoped-sudo sysctl.
#
# Usage: run_iperf_cell.sh <bw_mbps> <rtt_ms> <queue_pkts> <cca> <rep> <secs> <port>
set -u
BW=$1; RTT=$2; QP=$3; CCA=$4; REP=$5; SECS=$6; PORT=$7
OWD=$(( RTT / 2 ))
ROOT=/home/jaber/agentic-thin-waist
AIH=$ROOT/ai_cc/harness
OUTROOT=$ROOT/cc_classifier/phase2/train
SETTING="${BW}bw-${RTT}rtt-${QP}q"
RUNDIR="$OUTROOT/$SETTING/$CCA/$REP"
mkdir -p "$RUNDIR"
TRACE="$AIH/${BW}mbit.trace"
[ -f "$TRACE" ] || python3 "$AIH/gen_trace.py" "$BW" 12000 > "$TRACE"
DOWNLOG="$RUNDIR/down.log"
OCC="$RUNDIR/train_occupancy.csv"
CLILOG="$RUNDIR/iperf_client.json"

# 1) set the sender CCA globally (scoped passwordless sudo). The reverse-mode
#    server (the sender) inherits it at socket creation.
sudo -n sysctl -w net.ipv4.tcp_congestion_control="$CCA" >/dev/null 2>&1 || {
  echo "[cell] FAILED to set CCA $CCA"; exit 2; }
VERIFY=$(sysctl -n net.ipv4.tcp_congestion_control)
[ "$VERIFY" = "$CCA" ] || { echo "[cell] CCA mismatch: want $CCA got $VERIFY"; exit 2; }

# 2) fresh one-shot iperf3 server on the host (sender in reverse mode)
iperf3 -s -1 -p "$PORT" >/tmp/iperf_srv_${PORT}.log 2>&1 &
SRV=$!
sleep 0.5

T0=$(date +%s.%N)
# 3) client runs inside the mahimahi namespace; -R => server sends to client,
#    so bulk data traverses the shaped downlink (where the queue + log live).
INNERSH="$RUNDIR/inner.sh"
cat > "$INNERSH" <<INNEREOF
set -u
iperf3 -c "\$MAHIMAHI_BASE" -p $PORT -R -t $SECS -C $CCA -J > "$CLILOG" 2>/dev/null
true
INNEREOF

mm-delay "$OWD" mm-link "$TRACE" "$TRACE" \
  --downlink-queue=droptail --downlink-queue-args="packets=$QP" \
  --downlink-log="$DOWNLOG" -- bash "$INNERSH"
T1=$(date +%s.%N)
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null

# 4) occupancy @ 20 Hz + basic accounting
python3 "$AIH/queue_occupancy.py" "$DOWNLOG" 20 > "$OCC" 2>/dev/null
DELIV=$(awk '$2=="-"{s+=$3} END{print s+0}' "$DOWNLOG" 2>/dev/null)
DROPS=$(awk '$2=="d"{n++} END{print n+0}' "$DOWNLOG" 2>/dev/null)
NROWS=$(( $(wc -l < "$OCC" 2>/dev/null) - 1 ))
ELAPSED=$(awk "BEGIN{printf \"%.1f\", $T1-$T0}")

cat > "$RUNDIR/metadata.json" <<META
{"setting":"$SETTING","bandwidth_mbps":$BW,"base_rtt_ms":$RTT,"queue_pkts":$QP,
 "cca":"$CCA","workload":"iperf3-reverse","role":"training","rep":$REP,
 "duration_s_target":$SECS,"duration_s_actual":$ELAPSED,
 "bytes_delivered":$DELIV,"drops":$DROPS,"occupancy_rows":$NROWS}
META
echo "[cell] $SETTING/$CCA/rep$REP  deliv=${DELIV}B drops=${DROPS} occ_rows=${NROWS} (${ELAPSED}s)"
