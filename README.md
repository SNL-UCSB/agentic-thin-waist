# Agentic Thin Waist

A service-oriented platform for bottleneck-centric network data generation. Researchers describe an experiment in natural language, and the platform decomposes it into reproducible runs against shaped, instrumented infrastructure — with cross-traffic, traffic capture, and telemetry storage handled end-to-end.

## Quick Start

A five-minute walkthrough: bring the stack up, run one shaped wget download, pull its IDs, and open the analysis notebook. Concepts and reference live further down; this is just the happy path.

### Prerequisites
- macOS or Linux host with **Docker + Docker Compose v2** (Docker Desktop 24+ works).
- **`sudo`** (only if your user is not in the `docker` group — `docker compose up` needs to write to the docker socket).
- `curl` and `jq` on the host (used for status polling below).
- An LLM API key — `ANTHROPIC_API_KEY` *or* `GOOGLE_API_KEY` (set `ORCHESTRATOR_LLM_PROVIDER=gemini` if you use Google).
- Python 3.10+ with `jupyter` only if you want to run the analysis notebook locally (otherwise open it in the VS Code Jupyter extension).

### 1. Boot the stack
```bash
cp .env.example .env            # then edit .env and paste your API key
make build                      # docker compose build
make up                         # docker compose up -d, waits for /health, prints URLs
make status                     # docker compose ps — every service should be (healthy)
```

> Equivalent raw commands: `docker compose build && docker compose up -d && docker compose ps`.

### 2. Submit the wget intent
The orchestrator's `POST /intent` is the recommended entry point. The `context` block deterministically pins the queue size, AQM, CC, and duration so the parser does not have to infer them from the prose.

```bash
ORCH_ID=$(curl -s -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Run a wget download from https://speed.cloudflare.com/__down?bytes=10485760 over a 10 Mbps bottleneck with 20 ms added latency, pfifo queue, the queue size of 200 packets and cubic congestion control. One trial, 30 seconds",
    "workflow_source": "library",
    "context": {
      "aqm_policy": "pfifo",
      "buffer_packets": 200,
      "qdisc_params": {},
      "cc_algorithms": ["cubic"],
      "duration_seconds": 30,
      "num_trials": 1
    }
  }' | jq -r .orchestration_id)
echo "orchestration_id = $ORCH_ID"
```

### 3. Watch the experiment run
```bash
while STATUS=$(curl -s http://localhost:8005/orchestration/$ORCH_ID | jq -r .status); \
      [ "$STATUS" != "complete" ] && [ "$STATUS" != "failed" ]; do
  echo "$(date +%T) $STATUS"
  sleep 5
done
echo "final: $STATUS"
```

Expect ~1.5–2 minutes total: ephemeral worker provisioning, the synchronized capture + run window (30 s shaped wget), then artifact upload to telemetry.

### 4. Pull the experiment + result IDs
```bash
EXP=$(curl -s http://localhost:8005/orchestration/$ORCH_ID/results \
        | jq -r '.results[0].experiment_id')
RID=$(curl -s "http://localhost:8004/results?experiment_id=$EXP&limit=1" \
        | jq -r '.results[0].result_id')
echo "exp=$EXP  rid=$RID"
```

### 5. Analyze in the notebook
Open [services/analysis/analyze_queue.ipynb](services/analysis/analyze_queue.ipynb) and paste the printed `$EXP` value into the second code cell:

```python
EXPERIMENT_ID = os.environ.get('EXPERIMENT_ID', 'PASTE-$EXP-HERE')
```

Then **Run All**. The notebook will:
1. Hit `http://localhost:8004` (telemetry) and download the pcap + queue_trace.
2. Print a contextual-tree summary (you should see `buffer_packets: 200`, `qdisc: pfifo`).
3. Plot download/upload throughput (from pcap), bottleneck queue occupancy, and drop rate (from `/qtrace`). For a successful run, the download queue (`veth2`, blue) saturates at the 200-packet limit and the drop-rate panel spikes during the bulk transfer.

Tip: skip the manual paste with
```bash
EXPERIMENT_ID=$EXP jupyter nbconvert --to notebook --execute --inplace services/analysis/analyze_queue.ipynb
```

### 6. Tear everything down
```bash
make down                       # stop containers, keep volumes (fast restart)
make clean                      # docker compose down -v + remove pyc/pytest caches
```

`make clean` deletes telemetry's Postgres + MinIO volumes too, so any previously-stored experiment results are wiped — use `make down` if you want to keep them around.

## Vision

Progress in networking research depends on data that captures how applications and protocols respond to diverse, time-varying bottleneck regimes. Generating such data systematically is hard: bottleneck dynamics are simultaneously behavior-defining and execution-dependent, making them hard to replicate, vary, or reuse across environments.

This platform applies the **hourglass design** from netUnicorn to network data generation. The "thin waist" is a composable set of services that bridges diverse research intents (top) with diverse infrastructure (bottom):

```
                RESEARCH INTENTS
    Replication | Counterfactual | Pre-training | Broadband
    Teaching    | DOE Synthesis  | Benchmarking | Hypothesis
   ─────────────────────────────────────────────────────────
          \          any researcher, any question          /
           \                                              /
            ────────────────────────────────────────────
            |           AGENTIC THIN WAIST             |
            |                                          |
            |  Orchestration   (LLM + LangGraph)       |
            |  Experiment API + CTP + Substrate Worker |
            |     ├─ Intent          (Link/Bottleneck) |
            |     ├─ Representation  (CTPs)            |
            |     └─ Execution       (tc, tshark, …)   |
            |  NetGent Service  (application workflows)|
            |  Telemetry Service                       |
            |                                          |
            ────────────────────────────────────────────
           /                                            \
          /          any Docker-capable host              \
   ─────────────────────────────────────────────────────────
    Laptop Docker | AWS EC2 | PINOT Campus | ANL/ESnet
    Mininet       | Azure   | SNL Servers  | NetUnicorn
```

Researchers specify intents at the top. Agents orchestrate execution through the waist. Infrastructure adapts at the bottom.

## Progressive Disaggregation

The architecture is guided by **progressive disaggregation**, developed across our prior systems:

- **netUnicorn** — separates *what* to collect from *how* to realize it, and disaggregates intents into reusable tasks.
- **NetForge / NetReplica** — disaggregates bottleneck-centric data generation along three dimensions: intent vs. execution, static vs. dynamic attributes, and trace vs. context (via Cross-Traffic Profiles).
- **BQT+** — disaggregates workflow specification from execution for web-based measurement, modeling consumer-facing interfaces as nondeterministic finite automata.
- **NetGent** — extends BQT+'s NFA abstraction to general application workflows (YouTube, Netflix, Zoom, …), compiling natural-language workflow specs into executable state machines.

Together, these systems form the building blocks of the thin-waist platform.

## Architecture

```
  CONTROL PLANE                              DATA PLANE
  (researcher / SNL server)                  (wherever experiments run)
 ┌──────────────────────────────────┐       ┌──────────────────────────┐
 │                                  │       │                          │
 │  Orchestration  :8005            │ specs │  Substrate Workers :8002 │
 │  (LLM + LangGraph + OpenClaw)    │──────►│  (tc, tshark, tcpreplay) │
 │                                  │       │                          │
 │  Experiment API :8000            │       │  Browserless +           │
 │  (intent plane)                  │       │  NetGent worker          │
 │                                  │       │  (app workflows)         │
 │  CTP Service    :8001            │       │                          │
 │  (representation plane)          │results│                          │
 │                                  │◄──────│                          │
 │  NetGent Service:8003            │       │                          │
 │  Telemetry      :8004            │       │                          │
 └──────────────────────────────────┘       └──────────────────────────┘
                                            (PCAPs, tcp-info, metrics)
```

The **Control Plane** runs on the researcher's machine or an SNL server. The **Data Plane** runs wherever experiments execute — locally via Docker, on AWS EC2 in hybrid mode, or in future on remote campus hosts.

### Core Services

| Service | Port | Plane | Purpose |
|---|---|---|---|
| **Experiment API** | 8000 | Intent | Receives experiment specs, coordinates CTP + Substrate, persists status. |
| **CTP Service** | 8001 | Representation | Stores Cross-Traffic Profiles. Supports `extract`, `select`, `transform`, `merge`, `replay`. |
| **Substrate Worker** | 8002 | Execution | Applies tc qdisc/netem, runs tshark capture, replays CTP via tcpreplay. Sole owner of all kernel-level network operations. |
| **NetGent Service** | 8003 | Application | Browser/shell workflow engine (NFA-based). Async job API. |
| **Telemetry Service** | 8004 | Storage | Stores results + artifacts (PCAPs, JSON), exposes filtered queries. |
| **Orchestration** | 8005 | Agentic | NL intent → ParsedIntent → Cartesian product of experiments → end-to-end execution. |

### How a Single Experiment Runs

1. Orchestrator parses the NL intent (LLM call) into `ParsedIntent`.
2. `ExperimentGenerator` expands it into one `GeneratedExperiment` per (capacity × latency × CC) combination, each with a globally-unique ID (see *Experiment IDs* below).
3. For each spec, the orchestrator:
   - Provisions an ephemeral substrate worker (local Docker by default).
   - Picks a CTP from the CTP Service that matches the intensity range.
   - Tells the worker to fetch the CTP PCAPs.
   - Synchronizes three actions on the next whole-minute boundary: start tshark capture, start `tcpreplay-edit` background traffic, and start the application workflow.
   - Stops replay, drains capture, streams the resulting PCAP to telemetry.
   - Destroys the worker.

## Detailed Setup & Reference

The Quick Start above covers the happy path. This section is the reference: full prerequisite list, every `make` / `docker compose` target, the generic `/intent` payload (any application, not just wget), and direct calls into the lower-level services for debugging.

### Prerequisites
- Docker + Docker Compose (24+).
- Python 3.10+ (for local development).
- An LLM API key — `ANTHROPIC_API_KEY` (default) or `GOOGLE_API_KEY` (if you switch the orchestrator to Gemini).

### 1. Clone and configure
```bash
git clone git@github.com:SNL-UCSB/agentic-thin-waist.git
cd agentic-thin-waist
cp .env.example .env        # then edit .env with your API key + paths
```

### 2. Build and start the stack
```bash
docker compose build                       # build all images
sudo docker compose up -d                       # start everything (detached)
docker compose ps                          # service status
docker compose logs -f                     # tail logs for everything
docker compose logs -f orchestration       # tail one service
docker compose down                        # stop
docker compose down -v                     # stop + remove volumes
```

Equivalent `make` shortcuts are defined in the [Makefile](Makefile):

| Make target | Underlying command | Extras |
|---|---|---|
| `make build` | `docker compose build` | — |
| `make up` | `docker compose up -d` | polls `localhost:8000/health` for up to 30s, then prints service URLs |
| `make status` | `docker compose ps` | — |
| `make logs` | `docker compose logs -f` | — |
| `make logs-service SERVICE=<x>` | `docker compose logs -f <x>` | — |
| `make down` | `docker compose down` | — |
| `make clean` | `docker compose down -v` | also removes `__pycache__`, `*.pyc`, `.pytest_cache`, `build/`, `dist/`, `*.egg-info` |

Once the stack is up, the services are reachable on:

```
Experiment API     http://localhost:8000
CTP Service        http://localhost:8001
Substrate Worker   http://localhost:8002
NetGent Service    http://localhost:8003
Telemetry          http://localhost:8004
Orchestration      http://localhost:8005
```

### 3. Submit a research intent
The recommended entry point is the orchestrator's `POST /intent`:

```bash
curl -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Run iperf3 at 40 Mbps with 100 ms latency under cubic and bbr",
    "context":     { "duration_seconds": 60, "num_trials": 1 },
    "preferences": {},
    "workflow_source": "auto"
  }'
```

The response is `202 Accepted` with an `orchestration_id`. Track progress and pull results:

```bash
curl http://localhost:8005/orchestration/<orch_id>            # status + per-experiment progress
curl http://localhost:8005/orchestration/<orch_id>/results    # aggregated results
curl http://localhost:8005/orchestration/<orch_id>/reasoning  # agent reasoning trace
```

The orchestrator generates one experiment per (capacity × latency × CC) combination, each with an ID like `iperf3_40_40_100_pfifo_cubic_a2d6e73d`.

`workflow_source` controls where the NetGent workflow comes from:

| Value | Meaning |
|---|---|
| `auto` (default) | LLM picks a confident match from the workflow library; if none, the LLM generates a fresh workflow. |
| `library` | Library only — fail if no match. |
| `generate` | Skip the library, always generate. |

Pin a specific workflow with `"workflow_id": "test_ndt_workflow"` (overrides `workflow_source`). The deployment-wide default for `workflow_source` is `ORCH_DEFAULT_WORKFLOW_SOURCE` (defaults to `auto`).

### 4. (Optional) Talk to the lower-level services directly
You can bypass the orchestrator and exercise individual services for debugging or scripted runs:

```bash
# CTP selection
curl -X POST http://localhost:8001/ctps/select -H 'Content-Type: application/json' \
  -d '{"intensity_range_mbps":[1,10]}'

# Apply traffic shaping on a substrate worker
curl -X POST http://localhost:8002/shape -H 'Content-Type: application/json' \
  -d '{"download_mbps":40,"upload_mbps":40,"latency_ms":100,"qdisc":"pfifo"}'

# Start replay (note PNAT default — see below)
curl -X POST http://localhost:8002/replay -H 'Content-Type: application/json' \
  -d '{"ctp_file":"cluster26_tree10_profile424",
       "pnat":"169.231.0.0/16:172.16.1.20,128.111.0.0/16:172.16.1.20",
       "duration_seconds":60}'
```

Each service's README documents its full HTTP surface:
- [services/experiment-api/README.md](services/experiment-api/README.md)
- [services/ctp-service/README.md](services/ctp-service/README.md)
- [services/substrate-worker/README.md](services/substrate-worker/README.md)
- [services/netgent-service/README.md](services/netgent-service/README.md)
- [services/telemetry-service/README.md](services/telemetry-service/README.md)
- [services/orchestration/README.md](services/orchestration/README.md)

## Recently-Changed Surface Area

A few knobs landed recently that may not be documented elsewhere:

### Experiment ID format
Each generated experiment gets a globally-unique, descriptive ID:

```
{app}_{download_mbps}_{upload_mbps}_{latency_ms}_{aqm}_{cc}_{uuid8}
# e.g. iperf3_40_40_100_pfifo_cubic_a2d6e73d
#      youtube_25_25_50_fq_codel_bbr_77856217
```

`app` is taken from the first entry of `parsed_intent.applications` (slugified to lowercase alphanumerics), falling back to `application_type` (`shell` / `browser`). When `TELEMETRY_SERVICE_URL` is configured, each candidate ID is also checked against `GET /results?experiment_id=<id>&limit=1` so it can't collide with anything already persisted. Implementation: [`services/orchestration/app/engine/experiment_generator.py`](services/orchestration/app/engine/experiment_generator.py).

### CTP is opt-in (no default cross-traffic)
If the intent does not mention cross-traffic, the orchestrator now treats CTP as absent: `ctp_cluster` and `ctp_capacity_range` stay `null`, `_select_ctp` short-circuits to `None`, and `/replay` is skipped on the worker. Previously a silent 1–10 Mbps default was synthesized, which polluted every captured pcap with `172.16.1.20` packets the user hadn't asked for.

To opt in, the intent (or `context`) must populate `ctp_capacity_range` (`{"lower_value": float, "higher_value": float}` in Mbps) or `ctp_cluster`. Implementation: [`services/orchestration/app/engine/orchestration_manager.py`](services/orchestration/app/engine/orchestration_manager.py) (`_select_ctp`) and [`services/orchestration/app/engine/experiment_generator.py`](services/orchestration/app/engine/experiment_generator.py).

### CTP replay PNAT
When CTP *is* requested, background cross-traffic is replayed by the substrate worker via `tcpreplay-edit --pnat=…`. The default rule sends replayed packets to **`172.16.1.20`** — distinct from the application's interface IP (`172.16.1.1`) — so a captured PCAP can be split between application traffic and replayed cross-traffic by IP.

Override per experiment: set `replay_pnat_ip` on `GeneratedExperiment` (a single target IP; the standard source subnets `169.231.0.0/16` and `128.111.0.0/16` are reused).
Override globally: set `SUBSTRATE_REPLAY_PNAT` to a full rewrite rule.

Details and resolution order: [`services/orchestration/README.md` § CTP Replay & PNAT](services/orchestration/README.md#ctp-replay--pnat).

### Workloads always run inside ns1
The substrate worker now forces every shell workflow dispatched via `POST /run` to execute inside the `ns1` network namespace (via `nsenter -- ip netns exec ns1 <cmd>`), regardless of what `NETGENT_USE_LOCAL` / `NETGENT_NAMESPACE` are set to in the container environment. This is hardcoded at module load in [`services/substrate-worker/src/substrate/main_local.py`](services/substrate-worker/src/substrate/main_local.py) (and the `main.py` / `main_aws.py` siblings).

Why: with the old default, wget/iperf/etc. ran in the worker's root namespace and reached the internet via `eth0`, so the pcap on `veth2` only ever captured the substrate's iperf3 self-test instead of the actual workload. The fix routes the workload through the shaped veth pair so the existing tc rules apply to its packets.

### Shell-command deadline (`experiment_max_seconds`)
Today's wget / iperf / ping / ndt adapters have no wallclock cap of their own (wget's `--timeout` only fires on stalls), so a slow-but-progressing workload would run past the capture window. The substrate worker now bounds every shell command by a wallclock deadline:

- The orchestrator passes `spec.duration_seconds` as `experiment_max_seconds` on the `/run` payload.
- The substrate worker monkey-patches NetGent's `run_subprocess` to honor it. On timeout it sends SIGTERM, waits 2 s, then SIGKILL.
- Partial stdout/stderr written before the kill are preserved and returned with `returncode=124` (coreutils `timeout(1)` convention).
- The `/run` response carries `terminated_at_deadline: bool`. The pcap, qtrace, and telemetry `POST /results` all proceed as if the workflow completed normally — only the inner action shows a non-zero rc.

So a 50 MiB download on a 10 Mbps / 30 s experiment now terminates cleanly at the deadline with `terminated_at_deadline=true`, ~8 MiB visible in the pcap, and the experiment row marked `success`. Applies to every shell adapter that goes through `run_subprocess` (wget, iperf, ping, ndt); browser/playwright workflows have no deadline yet. Disable by omitting `duration_seconds` (no upper bound applied).

Implementation: top of [`services/substrate-worker/src/substrate/main_local.py`](services/substrate-worker/src/substrate/main_local.py); tests in [`services/substrate-worker/tests/test_shell_deadline.py`](services/substrate-worker/tests/test_shell_deadline.py).

### Workflow source on the intent request
The choice between "use the workflow library" and "have the LLM generate a workflow" is now a request property, not a deployment env var. Fields on `ResearchIntent`:

- `workflow_source`: `"auto"` (default — library first, fall back to generation) / `"library"` (fail if no match) / `"generate"` (skip the library).
- `workflow_id`: explicit pin (e.g. `"test_ndt_workflow"`) — overrides `workflow_source`.

Library selection is LLM-driven against the NetGent workflow index. The previous keyword inference (`iperf` → `test_iperf_workflow`, etc.) and the `ORCH_FORCE_EXISTING_WORKFLOW` / `ORCH_FORCE_WORKFLOW_ID` env vars are gone. Deployments can set `ORCH_DEFAULT_WORKFLOW_SOURCE` to change the default when the request doesn't specify one.

Details: [`services/orchestration/README.md` § Workflow Source](services/orchestration/README.md#workflow-source).

### Queue size + queue-occupancy traces
Bottleneck queue size is now a first-class experiment parameter. Pass it deterministically in `context`:

```jsonc
"context": {
  "buffer_packets": 100,                      // pfifo / bfifo / sfq
  "qdisc_params": {"limit": "500"}            // AQM qdiscs (fq_codel / codel / cake)
}
```

Every experiment also captures a **queue-occupancy trace** via the substrate worker's `/qtrace` endpoint — `tc -s` polled at 5 ms cadence on `veth2` and `veth4`, uploaded to telemetry as a `queue_trace` artifact next to the pcap. Plot it with [`services/analysis/analyze_queue.ipynb`](services/analysis/analyze_queue.ipynb) — the notebook now lays out **download throughput** (left), **upload throughput** (right), and per-interface queue occupancy / drop rate on a shared time axis. Disable globally with `ORCH_QTRACE_ENABLED=false`.

The split uses two new pcap helpers re-exported from `services.analysis`: `filter_downlink(pkts)` keeps packets with `ip.dst == 172.16.1.1` and `filter_uplink(pkts)` keeps packets with `ip.src == 172.16.1.1` (the app client lives in `ns1` on `172.16.1.1`). On the queue side, `veth2` is the root↔ns1 leg → download queue, `veth4` is the root↔ns2 leg → upload queue.

Details: [`services/orchestration/README.md` § Queue-Occupancy Trace](services/orchestration/README.md#queue-occupancy-trace-qtrace) and [`services/substrate-worker/README.md` § POST /qtrace](services/substrate-worker/README.md#post-qtrace).

## Repository Layout

```
agentic-thin-waist/
├── README.md                   # this file
├── docker-compose.yml          # local dev stack
├── docker-compose.cloud.yml    # AWS hybrid mode
├── docker-compose.test.yml     # CI test stack
├── Makefile                    # common tasks
├── .env.example                # template — copy to .env and fill in
│
├── services/
│   ├── experiment-api/                   # Intent plane (port 8000)
│   ├── ctp-service/                      # Representation plane (port 8001)
│   ├── substrate-worker/                 # Execution plane (port 8002)
│   ├── browserless-substrate-worker/     # Headless browser pool, shares ns w/ substrate-worker
│   ├── netgent-service/                  # App workflow engine (port 8003)
│   ├── telemetry-service/                # Results + artifact storage (port 8004)
│   ├── orchestration/                    # NL intent → experiments (port 8005)
│   ├── netforge-setup/                   # Substrate provisioning helpers
│   └── analysis/                         # Result-analysis package + notebooks
│
├── shared/
│   ├── models/                           # Dataclass contracts shared across services
│   ├── clients/                          # Service client libraries
│   ├── db/                               # Shared DB utilities
│   ├── s3/                               # MinIO/S3 helpers
│   └── tests/
│
├── docs/
│   ├── vision.md
│   ├── thin_waist_one_pager.md
│   ├── demo_plan_april_2026.md
│   ├── lit-survey/
│   └── user_study/
│
└── tests/                                # Cross-service integration tests
```

## Development

### Build & test
```bash
docker compose build                       # all Docker images
docker compose up -d                       # start stack

# Full test suite (runs orchestration-tests container, exits when done)
docker compose -f docker-compose.yml -f docker-compose.test.yml \
  up --build --abort-on-container-exit --exit-code-from orchestration-tests \
  orchestration-tests
# or: make test

# Repo-level pytest (no containers)
pytest tests/ -v
# or: make test-local

# Single-service test runs
cd services/<name> && pytest tests/ -v
cd services/<name> && pytest tests/ -v --cov=app --cov-report=term-missing
cd shared && pytest tests/ -v
```

### Formatting
Black is the only enforced formatter. CI pins `black==26.3.1` and only checks changed `.py` files on PRs.

```bash
black services/ shared/ tests/
black --check services/ shared/ tests/
```

### Branch & commit conventions
- Branch naming: `<username>/<area>/<short-description>` (e.g. `jaber/orchestration/fix-replay`).
- Commit prefix: the service or area being touched, e.g. `orchestration: …`, `substrate-worker: …`, `shared: …`.
- One logical change per PR.

### CI pipeline
GitHub Actions runs per-service on PRs touching that service's path or `shared/`. Each service workflow builds the image, runs `pytest` inside it, then starts the service via Compose to verify it comes up healthy. `black.yml` checks formatting on changed files; `shared-tests.yml` runs the shared library tests when `shared/` changes.

## Deliverables

| ID | Lead | Service(s) | Status |
|---|---|---|---|
| **D1** — NetForge Service (Intent / Representation / Execution) | Jaber, Satyam, Snithik | experiment-api, ctp-service, substrate-worker | Active |
| **D2** — NetGent Programmatic API | Eugene + Jaber | netgent-service | Active |
| **D3** — Telemetry & Storage Pipeline | Manni | telemetry-service | Active |
| **D4** — Evaluation Pipeline | — | analysis | Stretch |
| **D5** — Agentic Orchestration | Haarika | orchestration | Active — NL intent end-to-end working |

## Key Concepts

### Bottleneck regime
A bottleneck regime comprises (i) a **static envelope** — capacity, base latency, buffering, and queue management — and (ii) a **time-varying congestion-pressure process** that drives contention within that envelope. NetForge makes this explicit by disaggregating static and dynamic attributes into independently controllable specs.

### Cross-Traffic Profile (CTP)
A reusable representation of dynamic congestion pressure applied at a bottleneck. CTPs encode the temporal structure of aggregate demand — intensity, burstiness, heterogeneity, temporal correlations — without binding to the path, applications, or users that produced it. Operations: `extract`, `select`, `transform`, `merge`, `replay`.

### Experiment lifecycle
1. **Intent** — researcher expresses goal in natural language (or a structured spec).
2. **Decomposition** — orchestration parses intent and generates one experiment per parameter combination.
3. **Static spec** — capacity, latency, buffer, AQM applied via tc.
4. **Dynamic spec** — CTP selected from the corpus.
5. **Execution** — Substrate Worker applies shaping, runs CTP replay, runs the application workflow.
6. **Collection** — tshark captures upstream and downstream PCAPs.
7. **Storage** — results + PCAPs persisted to Telemetry Service, tagged with full context.

### Four requirements (from NetForge)
**Controllability** (independent knobs for intent, static structure, and dynamic pressure), **composability** (mix-and-match), **replicability** (same specs re-instantiate comparable regimes across runs), and **fidelity** (preserve realistic queueing signals and closed-loop application–bottleneck interaction).

## References

- netUnicorn (CCS '23) — Data-collection platform with hourglass design and SOA.
- NetForge (SIGCOMM submission #1035) — Programmable substrate for bottleneck-centric data generation.
- BQT+ (SIGCOMM '26 submission) — NFA-based broadband plan measurement.
- NetReplica — private SNL-UCSB repo.
- Linux Traffic Control: https://man7.org/linux/man-pages/man8/tc.8.html

## Team

- **PI**: Prof. Arpit Gupta (SNL-UCSB)
- **Org**: [SNL-UCSB](https://github.com/SNL-UCSB)
- **Repository**: [github.com/SNL-UCSB/agentic-thin-waist](https://github.com/SNL-UCSB/agentic-thin-waist) (private)

## License

Proprietary — SNL-UCSB. All rights reserved.
