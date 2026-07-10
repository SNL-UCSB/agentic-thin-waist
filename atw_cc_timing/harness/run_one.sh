#!/usr/bin/env bash
# Run ONE ATW experiment with phase-resolved timing + orchestrator token accounting.
#
# Phases captured (all epoch seconds):
#   t_health_start/done   : pre-submit health probe of all 6 services
#   t_cc_set              : host sender CC applied + verified (sysctl)
#   t_submit / t_submit_done : POST /intent round-trip
#   t_parsing/t_generating/t_executing/t_terminal : first-seen orchestration status
#   t_shaping_applied     : first time substrate /state shows bottleneck (spin-up done); "" if ephemeral
#   t_transfer_start/end  : qtrace first/last epoch sample on the bottleneck iface (post-hoc)
#   t_result_available    : telemetry result row queryable (drain+upload done)
#
# Usage: run_one.sh <idx> <bw> <rtt> <q> <cc> <dur>
set -u
IDX=$1; BW=$2; RTT=$3; Q=$4; CC=$5; DUR=$6
ROOT=/home/jaber/agentic-thin-waist
TROOT=$ROOT/atw_cc_timing
TAG=$(printf "%02d_%dbw-%drtt-%dq_%s" "$IDX" "$BW" "$RTT" "$Q" "$CC")
RUNDIR=$TROOT/runs/$TAG
mkdir -p "$RUNDIR"
PHASES=$RUNDIR/phases.env
: > "$PHASES"
now(){ date +%s.%N; }
rec(){ echo "$1=$2" >> "$PHASES"; }

echo "[$TAG] start $(date -u +%H:%M:%S)"
rec tag "$TAG"; rec idx "$IDX"; rec bw "$BW"; rec rtt "$RTT"; rec q "$Q"; rec cc "$CC"; rec dur "$DUR"

# ---- healthcheck phase ----
t=$(now); rec t_health_start "$t"
HEALTH_OK=1
for p in 8000 8001 8002 8003 8004 8005; do
  curl -s --max-time 5 "http://localhost:$p/health" >/dev/null 2>&1 || \
  curl -s --max-time 5 "http://localhost:$p/" >/dev/null 2>&1 || HEALTH_OK=0
done
t=$(now); rec t_health_done "$t"; rec health_ok "$HEALTH_OK"

# ---- set host sender CC (cc.md §3) ----
sudo -n sysctl -w net.ipv4.tcp_congestion_control="$CC" >/dev/null 2>&1
GOTCC=$(sysctl -n net.ipv4.tcp_congestion_control)
t=$(now); rec t_cc_set "$t"; rec cc_verified "$GOTCC"
if [ "$GOTCC" != "$CC" ]; then echo "[$TAG] WARN cc mismatch want=$CC got=$GOTCC"; fi

# ---- submit intent ----
INTENT="Run a wget download from http://128.111.5.237:8888/1GB.bin over a ${BW} Mbps bottleneck with ${RTT} ms added latency, pfifo queue of ${Q} packets and ${CC} congestion control. Do not store the downloaded file (write it to /dev/null). Stop the wget process after ${DUR} seconds. One trial."
echo "$INTENT" > "$RUNDIR/intent.txt"
# Pin the bundled wget workflow (workflow_id overrides workflow_source) — this is
# the deterministic path; the 'auto'/generate route hits a flaky LangGraph
# "decide" sync/async bug ~half the time and is not representative timing.
BODY=$(python3 - "$INTENT" "$BW" "$RTT" "$CC" "$Q" "$DUR" <<'PY'
import json,sys
intent,bw,rtt,cc,q,dur=sys.argv[1:7]
print(json.dumps({"intent":intent,"workflow_source":"library","workflow_id":"test_wget_workflow","context":{
 "capacities":[float(bw)],"latencies":[float(rtt)],"cc_algorithms":[cc],
 "aqm_policy":"pfifo","buffer_packets":int(q),"qdisc_params":{},
 "duration_seconds":int(dur),"num_trials":1}}))
PY
)
t=$(now); rec t_submit "$t"
RESP=$(curl -s -X POST http://localhost:8005/intent -H "Content-Type: application/json" -d "$BODY")
t=$(now); rec t_submit_done "$t"
echo "$RESP" > "$RUNDIR/intent_response.json"
ORCH=$(echo "$RESP" | python3 -c "import json,sys;print(json.load(sys.stdin).get('orchestration_id',''))" 2>/dev/null)
rec orch_id "$ORCH"
if [ -z "$ORCH" ]; then echo "[$TAG] FAILED submit"; rec fail submit; exit 0; fi

# ---- fine-grained poll: status transitions + shaping-applied ----
declare -A SEEN
SHAPED=""
TERM=""
for i in $(seq 1 900); do   # up to ~450s at 0.5s
  ST=$(curl -s --max-time 5 "http://localhost:8005/orchestration/$ORCH" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  nowt=$(now)
  if [ -n "$ST" ] && [ -z "${SEEN[$ST]:-}" ]; then SEEN[$ST]=$nowt; rec "t_status_$ST" "$nowt"; fi
  # detect shaping applied on the compose worker (may stay empty if ephemeral)
  if [ -z "$SHAPED" ]; then
    HASB=$(curl -s --max-time 3 http://localhost:8002/state | python3 -c "import json,sys;d=json.load(sys.stdin);print(1 if (d.get('bottleneck_state')) else 0)" 2>/dev/null)
    if [ "$HASB" = "1" ]; then SHAPED=$nowt; rec t_shaping_applied "$nowt"; fi
  fi
  if [ "$ST" = complete ] || [ "$ST" = failed ]; then TERM=$ST; rec t_status_terminal "$nowt"; rec final_status "$ST"; break; fi
  sleep 0.5
done
[ -z "$SHAPED" ] && rec t_shaping_applied ""

# ---- collect telemetry: experiment_id, result_id, artifacts ----
# Guard: only collect on a completed run with a real experiment_id, else we would
# query telemetry with an empty id and pull a STALE result from a prior run.
EXP=$(curl -s "http://localhost:8005/orchestration/$ORCH/results" | python3 -c "import json,sys;r=(json.load(sys.stdin).get('results') or [{}]);print(r[0].get('experiment_id','') if r else '')" 2>/dev/null)
rec experiment_id "$EXP"
t=$(now); rec t_collect_start "$t"
RID=""
if [ "$TERM" = complete ] && [ -n "$EXP" ]; then
  for i in $(seq 1 30); do
    RID=$(curl -s "http://localhost:8004/results?experiment_id=$EXP&limit=1" | python3 -c "import json,sys;r=(json.load(sys.stdin).get('results') or []);print(r[0].get('result_id','') if r else '')" 2>/dev/null)
    [ -n "$RID" ] && break; sleep 1
  done
else
  echo "[$TAG] skip collection (final=$TERM exp='$EXP')"
fi
t=$(now); rec t_result_available "$t"; rec result_id "$RID"

if [ -n "$RID" ]; then
  curl -s "http://localhost:8004/results/$RID" > "$RUNDIR/result.json"
  curl -s "http://localhost:8004/results/$RID/artifacts" > "$RUNDIR/artifacts.json"
  python3 -c "import json;[print(a['artifact_id'],a['artifact_type'],a['filename']) for a in json.load(open('$RUNDIR/artifacts.json')).get('artifacts',[])]" \
   | while read AID ATYPE FN; do
       curl -s "http://localhost:8004/artifacts/$AID" -o "$RUNDIR/${ATYPE}__${FN}"
     done
fi

# ---- transfer window from qtrace epochs (bottleneck iface = max-backlog iface) ----
QT=$(ls "$RUNDIR"/queue_trace__*.jsonl 2>/dev/null | head -1)
if [ -n "$QT" ]; then
  python3 - "$QT" "$PHASES" <<'PY'
import json,sys
qt,phases=sys.argv[1],sys.argv[2]
per={}
for line in open(qt):
    try: d=json.loads(line)
    except: continue
    ifc=d.get('iface'); per.setdefault(ifc,{'ts':[],'pk':[]})
    per[ifc]['ts'].append(d.get('t')); per[ifc]['pk'].append(d.get('backlog_pkts') or 0)
# bottleneck = iface with the largest max backlog
best=max(per, key=lambda k: max(per[k]['pk']) if per[k]['pk'] else -1)
ts=[x for x in per[best]['ts'] if x is not None]
with open(phases,'a') as f:
    f.write(f"qtrace_iface={best}\n")
    f.write(f"t_transfer_start={min(ts)}\n")
    f.write(f"t_transfer_end={max(ts)}\n")
    f.write(f"qtrace_samples={len(ts)}\n")
    f.write(f"backlog_max={max(per[best]['pk'])}\n")
PY
fi

# ---- orchestrator intent->config token cost (parse_intent) ----
PARSED=$(curl -s "http://localhost:8005/orchestration/$ORCH/reasoning" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for s in d.get('reasoning_steps',[]):
    if s.get('action')=='parse_intent':
        print(json.dumps(s.get('output',{}))); break
" 2>/dev/null)
echo "$PARSED" > "$RUNDIR/parsed_intent.json"
TOKS=$(python3 "$TROOT/harness/parse_tokens.py" both "$INTENT" "${PARSED:-{}}" 2>/dev/null)
IN_TOK=$(echo "$TOKS" | awk '{print $1}'); OUT_TOK=$(echo "$TOKS" | awk '{print $2}')
rec parse_in_tokens "${IN_TOK:-}"; rec parse_out_tokens "${OUT_TOK:-}"

echo "[$TAG] done final=$TERM exp=$EXP tokens_in=${IN_TOK} tokens_out=${OUT_TOK} $(date -u +%H:%M:%S)"
