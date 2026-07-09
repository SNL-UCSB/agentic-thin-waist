#!/usr/bin/env bash
# Run ONE Exp6 data-collection cell: download a large file over a single shaped
# mahimahi bottleneck under a chosen sender CCA, recording the bottleneck
# queue-occupancy trace (from mm-link's downlink log), a pcap, and metadata.
#
# Usage: run_cell.sh <bw_mbps> <rtt_ms> <queue_pkts> <cca> <rep> <port> <secs>
set -u
BW=$1; RTT=$2; QP=$3; CCA=$4; REP=$5; PORT=$6; SECS=$7
OWD=$(( RTT / 2 ))                      # mm-delay one-way; RTT = 2*OWD
ROOT=/home/jaber/agentic-thin-waist/ai_cc
SETTING="${BW}bw-${RTT}rtt-${QP}q"
RUNDIR="$ROOT/results/$SETTING/$CCA/$REP"
mkdir -p "$RUNDIR"
TRACE="$ROOT/harness/${BW}mbit.trace"
[ -f "$TRACE" ] || python3 "$ROOT/harness/gen_trace.py" "$BW" 12000 > "$TRACE"

DOWNLOG="$RUNDIR/down.log"
PCAP="$RUNDIR/capture.pcap"
WGETLOG="$RUNDIR/wget.log"
FILEURL_PATH="/bigfile.bin"
FSIZE=$(stat -c%s "$ROOT/srv/bigfile.bin")

T_START=$(date -u +%Y-%m-%dT%H:%M:%SZ); T0=$(date +%s.%N)

# Inner command runs inside the mahimahi network namespace (written to a file
# to avoid all shell-quoting hazards; only MAHIMAHI_BASE is resolved at runtime).
INNERSH="$RUNDIR/inner.sh"
cat > "$INNERSH" <<INNEREOF
set -u
iface=\$(ip -o link show | awk -F': ' '\$2!="lo"{print \$2; exit}')
dumpcap -i "\$iface" -f "tcp port $PORT" -w "$PCAP" -q &
DP=\$!
sleep 0.4
timeout $SECS wget -O /dev/null --header="Cache-Control: no-cache" \
    "http://\$MAHIMAHI_BASE:$PORT$FILEURL_PATH" 2> "$WGETLOG"
sleep 0.3
kill \$DP 2>/dev/null
wait \$DP 2>/dev/null
true
INNEREOF

echo "[run_cell] mm-delay $OWD mm-link $TRACE $TRACE --downlink-queue=droptail --downlink-queue-args=packets=$QP --downlink-log=$DOWNLOG -- bash $INNERSH"
mm-delay "$OWD" mm-link "$TRACE" "$TRACE" \
  --downlink-queue=droptail --downlink-queue-args="packets=$QP" \
  --downlink-log="$DOWNLOG" -- bash "$INNERSH"

T1=$(date +%s.%N); T_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ELAPSED=$(awk "BEGIN{printf \"%.2f\", $T1-$T0}")

# queue occupancy trace @ 20 Hz from the mm-link downlink log
python3 "$ROOT/harness/queue_occupancy.py" "$DOWNLOG" 20 > "$RUNDIR/queue_occupancy.csv"

# bytes delivered = sum of departures (bytes) in the downlink log
DELIV=$(awk '$2=="-"{s+=$3} END{print s+0}' "$DOWNLOG")
DROPS=$(awk '$2=="d"{n++} END{print n+0}' "$DOWNLOG")
PKTS=$(tcpdump -r "$PCAP" 2>/dev/null | wc -l)

cat > "$RUNDIR/metadata.json" <<META
{
  "setting": "$SETTING",
  "bandwidth_mbps": $BW,
  "base_rtt_ms": $RTT,
  "mm_delay_oneway_ms": $OWD,
  "queue_pkts": $QP,
  "queue_mgmt": "droptail-fifo",
  "cca": "$CCA",
  "cca_side": "sender (origin HTTP server, via setsockopt TCP_CONGESTION)",
  "download_tool": "wget",
  "origin_file_bytes": $FSIZE,
  "duration_s_target": $SECS,
  "duration_s_actual": $ELAPSED,
  "bytes_delivered_downlink_log": $DELIV,
  "downlink_drops": $DROPS,
  "pcap_packets": $PKTS,
  "t_start_utc": "$T_START",
  "t_end_utc": "$T_END",
  "emulation_cmd": "mm-delay $OWD mm-link <5mbit.trace> <same> --downlink-queue=droptail --downlink-queue-args=packets=$QP --downlink-log=... ",
  "rep": $REP
}
META
echo "[run_cell] done -> $RUNDIR (elapsed ${ELAPSED}s, delivered ${DELIV}B, drops ${DROPS})"
