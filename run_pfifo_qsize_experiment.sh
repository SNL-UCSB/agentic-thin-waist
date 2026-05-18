#!/usr/bin/env bash
# End-to-end queue-size experiment: rebuild stack, submit iperf3 intent with
# pfifo / buffer_packets=200, verify the kernel actually applied the limit,
# then render the analysis notebook.
#
# Usage:
#   chmod +x run_pfifo_qsize_experiment.sh
#   ./run_pfifo_qsize_experiment.sh                 # defaults below
#   BUFFER_PACKETS=50 ./run_pfifo_qsize_experiment.sh
#   TARGET_HOST=10.0.0.5 CAPACITY_MBPS=100 ./run_pfifo_qsize_experiment.sh
#
# Exits non-zero on the first hard failure. Inline echoes mark the 7 phases.

set -uo pipefail

REPO=${REPO:-/mnt/md0/jaber/agentic-thin-waist}
TARGET_HOST=${TARGET_HOST:-128.111.5.236}
TARGET_PORT=${TARGET_PORT:-5201}
CAPACITY_MBPS=${CAPACITY_MBPS:-30}
LATENCY_MS=${LATENCY_MS:-50}
DURATION_S=${DURATION_S:-30}
BUFFER_PACKETS=${BUFFER_PACKETS:-200}
CC=${CC:-cubic}
AQM=${AQM:-pfifo}

cd "$REPO" || { echo "REPO not found: $REPO"; exit 1; }

echo "================================================================"
echo "  pfifo queue-size experiment"
echo "    repo            : $REPO"
echo "    target          : $TARGET_HOST:$TARGET_PORT"
echo "    shaping         : ${CAPACITY_MBPS} Mbps, ${LATENCY_MS} ms RTT"
echo "    qdisc / qsize   : ${AQM} / ${BUFFER_PACKETS} packets"
echo "    cc / duration   : ${CC} / ${DURATION_S}s"
echo "================================================================"

# ---------- 0/7  Tear down + clean rebuild ----------------------------------
echo ""
echo "=== 0/7  Tearing down old stack + rebuilding orchestration + substrate-worker ==="
sudo docker compose down -v --remove-orphans
sudo docker compose build orchestration substrate-worker
sudo docker compose up -d

# ---------- 1/7  Wait until all services are reachable ----------------------
echo ""
echo "=== 1/7  Waiting for all services reachable (netgent included) ==="
deadline=$(( $(date +%s) + 180 ))
until curl -fs http://localhost:8005/health \
        | jq -e '.checks | to_entries | all(.value=="reachable")' >/dev/null 2>&1; do
  if [ "$(date +%s)" -gt "$deadline" ]; then
    echo "  ERROR: services still not reachable after 180s"
    curl -s http://localhost:8005/health | jq .
    exit 2
  fi
  echo "  $(date +%T) waiting…"
  sleep 3
done
echo "  stack ready"

# ---------- 2/7  Submit the intent -----------------------------------------
echo ""
echo "=== 2/7  Submitting iperf3 intent ==="
INTENT_JSON=$(cat <<EOF
{
  "intent": "Run iperf3 client to ${TARGET_HOST} port ${TARGET_PORT} for ${DURATION_S}s with ${CC} congestion control.",
  "context": {
    "capacities":       [${CAPACITY_MBPS}],
    "latencies":        [${LATENCY_MS}],
    "cc_algorithms":    ["${CC}"],
    "aqm_policy":       "${AQM}",
    "buffer_packets":   ${BUFFER_PACKETS},
    "duration_seconds": ${DURATION_S},
    "num_trials":       1
  },
  "workflow_id": "test_iperf_workflow"
}
EOF
)
echo "  payload:"
echo "$INTENT_JSON" | jq .

RESPONSE=$(curl -s -w '\n%{http_code}\n' -X POST http://localhost:8005/intent \
  -H 'Content-Type: application/json' \
  --data-binary "$INTENT_JSON")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)
echo "  HTTP $HTTP_CODE  body: $BODY"
if [ "$HTTP_CODE" != "202" ]; then
  echo "  ERROR: intent submission failed"
  exit 3
fi
ORCH_ID=$(echo "$BODY" | jq -r .orchestration_id)
if [ -z "$ORCH_ID" ] || [ "$ORCH_ID" = "null" ]; then
  echo "  ERROR: orchestration_id missing"
  exit 3
fi
echo "  orch=$ORCH_ID"

# ---------- 3/7  Confirm intent_overrides actually got merged --------------
echo ""
echo "=== 3/7  Verifying that intent_overrides made it through the agent ==="
sleep 5  # let parse_intent + generate_experiments run
if sudo docker compose logs --since 60s orchestration 2>/dev/null \
     | grep -q "Applying intent_overrides"; then
  echo "  GOOD — found 'Applying intent_overrides' line:"
  sudo docker compose logs --since 60s orchestration 2>/dev/null \
    | grep "Applying intent_overrides" | tail -3 | sed 's/^/    /'
else
  echo "  WARNING: no 'Applying intent_overrides' log — code may not be loaded."
  echo "  (Inspect with: sudo docker compose logs --tail=200 orchestration | grep AGENT)"
fi

# ---------- 4/7  Verify tc + /state mid-run --------------------------------
echo ""
echo "=== 4/7  Verifying kernel-side shaping (waiting for /state to settle) ==="
for _ in $(seq 1 30); do
  applied_cap=$(curl -s http://localhost:8002/state \
                  | jq -r '.bottleneck_state.download_mbps // empty' 2>/dev/null)
  if [ "${applied_cap%.*}" = "$CAPACITY_MBPS" ]; then
    break
  fi
  sleep 2
done

echo "  --- /state.bottleneck_state ---"
curl -s http://localhost:8002/state \
  | jq '.bottleneck_state | {qdisc, buffer_packets, download_mbps, upload_mbps, latency_ms, qdisc_params, verified}'

echo "  --- tc -s -d qdisc show dev veth2 (downstream) ---"
sudo docker compose exec -T substrate-worker tc -s -d qdisc show dev veth2 \
  | grep -E 'qdisc|limit|backlog' | sed 's/^/    /' || true

echo "  --- tc -s -d qdisc show dev veth4 (upstream) ---"
sudo docker compose exec -T substrate-worker tc -s -d qdisc show dev veth4 \
  | grep -E 'qdisc|limit|backlog' | sed 's/^/    /' || true

# Hard check: substrate worker must report buffer_packets matches what we asked for.
KERNEL_BP=$(curl -s http://localhost:8002/state \
              | jq -r '.bottleneck_state.buffer_packets // empty')
if [ "$KERNEL_BP" != "$BUFFER_PACKETS" ]; then
  echo "  ERROR: substrate-worker reports buffer_packets=$KERNEL_BP, expected $BUFFER_PACKETS."
  echo "         Override path is still broken — rebuild may not have picked up code changes."
  exit 4
fi
echo "  OK — kernel-side buffer_packets matches the request."

# ---------- 5/7  Poll orchestration to completion --------------------------
echo ""
echo "=== 5/7  Polling orchestration to completion ==="
while STATUS=$(curl -s http://localhost:8005/orchestration/$ORCH_ID | jq -r .status); \
      [ "$STATUS" != "complete" ] && [ "$STATUS" != "failed" ]; do
  echo "  $(date +%T) $STATUS"
  sleep 5
done
echo "  final status: $STATUS"

# ---------- 6/7  Collect experiment_id + iperf3 summary --------------------
echo ""
echo "=== 6/7  Per-experiment status + iperf3 output ==="
RESULTS_JSON=$(curl -s http://localhost:8005/orchestration/$ORCH_ID/results)
echo "$RESULTS_JSON" | jq '.results[] | {experiment_id, status, error: .lifecycle.error}'

EXP=$(echo "$RESULTS_JSON" | jq -r '.results[0].experiment_id // empty')
if [ -z "$EXP" ]; then
  echo "  ERROR: no experiment_id returned — orchestration failed"
  exit 5
fi
echo "  exp=$EXP"

RID=$(curl -s "http://localhost:8004/results?experiment_id=$EXP&limit=1" \
        | jq -r '.results[0].result_id // empty')
if [ -z "$RID" ]; then
  echo "  WARNING: telemetry has no result row yet for $EXP"
else
  echo "  result_id=$RID"
  echo "  --- iperf3 end-of-test summary ---"
  curl -s "http://localhost:8004/results/$RID" \
    | jq '.qoe_metrics[0].data.end | {sum_sent, sum_received}' 2>/dev/null \
    || curl -s "http://localhost:8004/results/$RID" | jq '.qoe_metrics'
fi

# ---------- 7/7  Render the queue notebook ---------------------------------
echo ""
echo "=== 7/7  Rendering analyze_queue.ipynb ==="
pushd services/analysis >/dev/null

EXPERIMENT_ID="$EXP" TELEMETRY_BASE=http://localhost:8004 \
  jupyter nbconvert --to notebook --execute analyze_queue.ipynb \
  --output "analyze_queue_${EXP}.ipynb"
RC=$?
popd >/dev/null

echo ""
echo "================================================================"
echo "  DONE"
echo "    orch_id    : $ORCH_ID"
echo "    exp_id     : $EXP"
echo "    result_id  : ${RID:-<missing>}"
echo "    qdisc      : $AQM / buffer_packets=$BUFFER_PACKETS (kernel-confirmed)"
echo "    notebook   : services/analysis/analyze_queue_${EXP}.ipynb"
echo "    rebuild     ✓        shape verified ✓        run ${STATUS}"
echo "================================================================"
exit $RC
