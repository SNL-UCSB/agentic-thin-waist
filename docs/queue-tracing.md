# Queue management & queue-occupancy tracing

This document covers the queue-related changes that landed on this branch: a
configurable bottleneck queue size at the experiment-spec level, a substrate-
worker `/qtrace` endpoint that records queue occupancy over time, and
analysis helpers + a notebook that plot the trace next to the PCAP. The goal
is CCAnalyzer-style queue evolution from the *real* qdisc — no eBPF, no BESS,
no offline simulation.

---

## Why

The repo already shapes a bottleneck with HTB + a child qdisc (`pfifo`,
`fq_codel`, `codel`, `cake`, …) on `veth2` / `veth4`. What was missing:

1. **No experiment-spec way to set queue size.** `buffer_packets` /
   `qdisc_params` existed on the substrate worker's `ShapeRequest`, but they
   weren't reachable from an intent — `ParsedIntent` and `GeneratedExperiment`
   didn't carry them, and the orchestrator hard-coded a `1000`-packet default.
2. **No way to observe queue occupancy.** PCAPs tell you what passed through
   the link, but not how full the qdisc backlog was at each moment — the
   exact signal CCAnalyzer (Mishra et al.) uses to distinguish Reno's
   sawtooth from Cubic's $x^3$ curve from BBR's periodic probes.

Both are now addressed.

---

## Architecture

```
intent JSON ────────────────────────────────────────► orchestration:8005
   "context": {                                          │
     "buffer_packets": 200,                              │  POST /intent
     "aqm_policy": "pfifo",                              ▼
     "qdisc_params": {...},                  ┌────────────────────────┐
     ...                                     │  intent_overrides[]    │
   }                                         │  merged into           │
                                             │  ParsedIntent          │
                                             └───────────┬────────────┘
                                                         │
                                                         ▼
                                             ┌────────────────────────┐
                                             │  ExperimentGenerator   │
                                             │   GeneratedExperiment  │
                                             │   .buffer_packets=200  │
                                             └───────────┬────────────┘
                                                         │
                                                         ▼
              ┌─────────────────────────────  OrchestrationManager  ──────────────────────────┐
              │                                                                                │
              │  fire @ next minute boundary (in parallel threads):                            │
              │                                                                                │
              │   ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐         │
              │   │  CAPTURE   │    │   QTRACE   │    │   REPLAY   │    │  WORKFLOW  │         │
              │   │  tshark    │    │  tc -s     │    │ tcpreplay  │    │  iperf/    │         │
              │   │  -> pcap   │    │  polling   │    │  CTP       │    │  ndt/wget  │         │
              │   └─────┬──────┘    └─────┬──────┘    └────────────┘    └─────┬──────┘         │
              │         │                  │                                    │              │
              └─────────┼──────────────────┼────────────────────────────────────┼──────────────┘
                        │                  │                                    │
                        ▼                  ▼                                    ▼
              ┌──────────────────────────────────────────────────────────────────────────┐
              │                            substrate-worker:8002                         │
              │                                                                          │
              │   POST /capture (tshark on veth2)                                        │
              │   POST /qtrace  (1+ interfaces, JSONL of qdisc backlog)                  │
              │   POST /replay  (tcpreplay-edit on veth1+veth3)                          │
              │   POST /run     (NetGent shell/browser workflow)                         │
              └────────────────────────────────────────┬─────────────────────────────────┘
                                                       │
                                                       ▼
                                        ┌──────────────────────────────┐
                                        │  telemetry:8004 /artifacts   │
                                        │  artifact_type="pcap"        │
                                        │  artifact_type="queue_trace" │
                                        └──────────────┬───────────────┘
                                                       │
                                                       ▼
                                       services/analysis/analyze_queue.ipynb
```

The qtrace thread is started at the **same minute-boundary** as capture and
replay (the existing tight-alignment design), so the pcap and the queue
trace share a clock origin within a few ms.

---

## Setting queue size from an intent

Deterministic overrides land in `context` and beat anything the LLM extracts:

```jsonc
{
  "intent": "Run iperf3 to 128.111.5.236 for 30s, cubic",
  "context": {
    "capacities":      [30],
    "latencies":       [50],
    "cc_algorithms":   ["cubic"],
    "aqm_policy":      "pfifo",       // pfifo / bfifo / pfifo_fast / sfq
    "buffer_packets":  200,           // queue depth in packets
    "duration_seconds": 30,
    "num_trials":      1
  },
  "workflow_id": "test_iperf_workflow"
}
```

For AQM qdiscs (`fq_codel`, `codel`, `cake`) — where `buffer_packets` is
ignored by design — set the limit via `qdisc_params.limit` instead:

```jsonc
"context": {
  "aqm_policy": "fq_codel",
  "qdisc_params": { "limit": "500", "target": "5ms", "interval": "100ms" }
}
```

**Heads up:** the substrate worker rejects `buffer_packets != 1000` for AQM
qdiscs with a 422. Use one knob or the other, not both.

### Plumbing (in case you need to trace it)

| Step | File | What it does |
|---|---|---|
| 1 | `services/orchestration/app/api/intent.py` | Extracts queue-related keys from `request.context` into `intent_overrides`. |
| 2 | `services/orchestration/app/agent/orchestrator/agent.py` (`generate_experiments`) | Merges `intent_overrides` into `parsed_intent` and **writes the merged dict back to state** so the downstream re-generation sees it. |
| 3 | `services/orchestration/app/agent/orchestrator/schemas.py` (`ParsedIntent`) | Adds `buffer_packets`, `qdisc_params`. |
| 4 | `services/orchestration/app/engine/experiment_generator.py` | Threads both fields into `GeneratedExperiment`. |
| 5 | `services/orchestration/app/models/schemas.py` (`GeneratedExperiment`) | Optional fields, default `None`. |
| 6 | `services/orchestration/app/engine/orchestration_manager.py` (`_fire_workflow`) | Forwards them to `ConnectivityManager.run_experiment` (None-safe — `None` falls back to `1000`). |
| 7 | `services/substrate-worker/src/substrate/main.py` (`POST /shape`) | Already accepted both fields; pre-existing validator catches conflicts. |

If after a rebuild `curl http://localhost:8002/state | jq .bottleneck_state.buffer_packets` doesn't match what you asked for, step 2 is the most common breakage — `generate_experiments` *must* return the merged `parsed_intent` because `execute_experiments` → `OrchestrationManager.run` regenerates specs from `state["parsed_intent"]`.

---

## Queue-occupancy trace (`/qtrace`)

`/qtrace` is a lightweight `tc -s` polling sampler — the **Option B** from the
design discussion, not eBPF, not BESS. It's good enough to see CCA fingerprints
without instrumenting the kernel.

### Endpoints (substrate-worker:8002)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/qtrace` | Start a background sampler on N interfaces. |
| `GET`  | `/qtrace/{id}` | Poll status (`running` / `finished`) and `samples_written`. |
| `GET`  | `/qtrace/{id}/trace` | Download the JSONL (only valid after `DELETE`). |
| `DELETE` | `/qtrace/{id}` | Stop the sampler; trace file retained. |

### Request

```json
{
  "interfaces": ["veth2", "veth4"],
  "filename": "iperf3_10mbps_qtrace",
  "interval_ms": 5,
  "duration_seconds": 30
}
```

The default cadence is 5 ms (≈ 200 samples/s/iface) — fine for typical
30 Mbps experiments and cheap on CPU. For sub-ms transients drop to `1`,
for low-frequency sanity checks bump to `20–50`.

### JSONL record schema

```json
{"t": 1716000000.123, "iface": "veth2",
 "backlog_bytes": 12345, "backlog_pkts": 12,
 "bytes_sent": 78901234, "pkts_sent": 56789,
 "drops": 0, "overlimits": 0}
```

All counter fields (`bytes_sent`, `pkts_sent`, `drops`, `overlimits`) are
**cumulative** — diff against the previous sample for the same interface to
get a rate. `services/analysis/queue_trace.py` does this for you.

### Leaf-qdisc selection

`tc -s -d qdisc show dev <iface>` lists every qdisc on the interface. The
sampler picks the leaf — `qdisc <name> 10:` — which is the child of the HTB
class `1:10` that carries the bottleneck queue. If for some reason the leaf
isn't found, the sampler falls back to the last stanza, but that's a
diagnostic hint that the topology has drifted.

### Orchestration knobs

| Env var | Default | Purpose |
|---|---|---|
| `ORCH_QTRACE_ENABLED`      | `true` | Disable the qtrace thread for a stack. |
| `ORCH_QTRACE_IFACES`       | `veth2,veth4` | Comma-separated interface list. |
| `ORCH_QTRACE_INTERVAL_MS`  | `5` | Sampling cadence. |
| `ORCH_CAPTURE_DURATION_SECONDS` | min(60, `duration_seconds`) | Reused by qtrace for the auto-stop. |

When the experiment finishes, the orchestrator stops the trace, GETs the
JSONL, and POSTs it to telemetry as a `queue_trace` artifact on the same
`result_id` as the pcap. See
`services/orchestration/app/engine/telemetry_qtrace_pull.py` for the upload
path.

---

## Analysis

```python
from services.analysis import (
    TelemetryClient,
    load_queue_trace, summarize_queue_trace,
    plot_queue_occupancy, plot_drop_rate,
)

client = TelemetryClient("http://localhost:8004")
bundle = client.fetch_experiment("iperf3_30_30_50_pfifo_cubic_xxxxxxxx")
paths  = client.download_qtraces(bundle, "./_pcap_cache")

df = load_queue_trace(paths[0])
print(summarize_queue_trace(df))   # min/p50/p95/p99/max backlog per iface
plot_queue_occupancy(df, unit="packets")
plot_drop_rate(df)
```

For the full picture (pcap throughput + queue occupancy + drops + iperf3
stdout), use the notebook **`services/analysis/analyze_queue.ipynb`**:

```bash
cd services/analysis
EXPERIMENT_ID="iperf3_30_30_50_pfifo_cubic_xxxxxxxx" \
TELEMETRY_BASE=http://localhost:8004 \
  jupyter nbconvert --to notebook --execute analyze_queue.ipynb \
  --output "analyze_queue_iperf3_30_30_50_pfifo_cubic_xxxxxxxx.ipynb"
```

The notebook has six cells: bundle summary → QoE / iperf3 stdout → pcap +
qtrace download → throughput / queue-pkts / drops side-by-side → CCAnalyzer
zoom (queue evolution in bytes for a chosen window) → per-trial repeat.

---

## Example experiments

### Single run — verify queue cap

`run_pfifo_qsize_experiment.sh` at the repo root is an end-to-end smoke test:

```bash
./run_pfifo_qsize_experiment.sh                       # 30 Mbps / 50 ms / pfifo 200pkts
BUFFER_PACKETS=50 CC=cubic ./run_pfifo_qsize_experiment.sh
TARGET_HOST=10.0.0.7 ./run_pfifo_qsize_experiment.sh
```

It tears down, rebuilds, asserts `intent_overrides` was applied, asserts
the kernel reports `buffer_packets` matches the request, runs the
experiment, and renders the notebook. Exit codes for each failure mode are
documented in the script header.

### Queue-size sweep (CCAnalyzer reproduction)

Hold CC, capacity, RTT constant; vary the queue:

```bash
for QSIZE in 50 200 1000; do
  ORCH_ID=$(curl -s -X POST http://localhost:8005/intent \
    -H 'Content-Type: application/json' \
    -d '{"intent":"Run iperf3 to 128.111.5.236 port 5201 for 30s, cubic.",
         "context":{"capacities":[30],"latencies":[50],
                    "cc_algorithms":["cubic"],"aqm_policy":"pfifo",
                    "buffer_packets":'"$QSIZE"',
                    "duration_seconds":30,"num_trials":1},
         "workflow_id":"test_iperf_workflow"}' \
    | jq -r .orchestration_id)
  echo "qsize=$QSIZE orch=$ORCH_ID"
done
```

Open the three rendered notebooks side by side. With cubic and pfifo, you
should see:

- **50 packets** — frequent loss, choppy throughput, tight sawtooth.
- **200 packets** — clean Cubic concave curve filling toward 200, drop, repeat.
- **1000 packets** — bufferbloat; queue stays nearly full; RTT inflated.

### CCA comparison at fixed queue

Hold queue size constant, vary CC:

```jsonc
"context": {
  "capacities":     [30],
  "latencies":      [50],
  "aqm_policy":     "pfifo",
  "buffer_packets": 200,
  "cc_algorithms":  ["cubic", "bbr"]
}
```

The orchestrator emits one experiment per CC. Iterate `bundle.results` in
the notebook and overlay queue traces.

---

## Implementation notes

- **Why polling instead of eBPF?** Polling `tc -s` is portable to every
  kernel that supports the iproute2 you already have; eBPF would be more
  precise (per-packet) but adds CONFIG_BPF + ABI-coupling and was an
  unnecessary complication for the first version. The plotted CCA
  signatures are clearly readable at 5 ms cadence.
- **Why not BESS?** BESS would give exact per-packet enqueue/dequeue
  events — the paper-faithful path — but replaces the whole shaping data
  plane. Defer until polling stops being enough.
- **Telemetry artifact schema.** `queue_trace` is a string `artifact_type`
  alongside `pcap`. No DB migration was needed — telemetry's artifact
  table already accepts arbitrary type strings.
- **Multiple interfaces.** veth2 (downstream) and veth4 (upstream) are
  both sampled by default. For external destinations the upload queue
  may actually live on the WAN interface (Docker `eth0` typically); add
  it to `ORCH_QTRACE_IFACES` if your study targets external hosts.

---

## Files changed by this feature

```
services/substrate-worker/src/substrate/main.py        # POST /qtrace endpoints + sampler
services/orchestration/app/agent/orchestrator/schemas.py   # ParsedIntent: buffer_packets, qdisc_params
services/orchestration/app/agent/orchestrator/agent.py     # intent_overrides plumbing
services/orchestration/app/agent/orchestrator/tools.py     # None-safe buffer_packets
services/orchestration/app/api/intent.py                   # context-override extraction
services/orchestration/app/engine/experiment_generator.py  # propagate to GeneratedExperiment
services/orchestration/app/engine/executor.py              # qtrace client methods + None-safe
services/orchestration/app/engine/orchestration_manager.py # fire qtrace alongside capture
services/orchestration/app/engine/telemetry_qtrace_pull.py # upload trace as artifact (new)
services/orchestration/app/models/schemas.py               # GeneratedExperiment fields
services/analysis/queue_trace.py                           # loader + plots (new)
services/analysis/client.py                                # qtrace_artifacts + download_qtraces
services/analysis/__init__.py                              # re-exports
services/analysis/analyze_queue.ipynb                      # new notebook
run_pfifo_qsize_experiment.sh                              # smoke-test script (new)
README.md, services/orchestration/README.md, services/substrate-worker/README.md   # docs
docs/queue-tracing.md                                      # this document (new)
```

---

## Future work

- **Sweep skill.** Wrap the queue-size sweep example as a Skill so it's
  one POST to `/skills/queue_size_sweep/execute`.
- **eBPF backend.** Add an optional `qtrace_backend=ebpf` that yields
  per-packet enqueue/dequeue events for high-resolution studies, while
  keeping polling as the default for portability.
- **Per-flow queue split.** The current trace is per-interface. For
  multi-flow studies (CTP background + iperf3) we'd want per-class
  backlogs — `tc -s class show dev veth2` instead of `tc -s qdisc show`.
- **AQM sweep helper.** A small wrapper that takes a list of qdisc
  configurations (pfifo @ N pkts, fq_codel @ N pkts, codel @ T target …)
  and emits one experiment per configuration with the right field set,
  rather than the caller juggling `buffer_packets` vs `qdisc_params.limit`.
