# Agentic Thin Waist

A service-oriented platform for bottleneck-centric network data generation. Researchers describe an experiment in natural language, and the platform decomposes it into reproducible runs against shaped, instrumented infrastructure — with cross-traffic, traffic capture, and telemetry storage handled end-to-end.

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

## Quick Start

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
make build                  # build all images
make up                     # start everything; waits on health checks
make status                 # docker compose ps
make logs                   # tail logs for everything
make logs-service SERVICE=orchestration   # tail one service
make down                   # stop
make clean                  # stop + remove volumes/caches
```

Once `make up` settles, the services are reachable on:

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
    "preferences": {}
  }'
```

The response is `202 Accepted` with an `orchestration_id`. Track progress and pull results:

```bash
curl http://localhost:8005/orchestration/<orch_id>            # status + per-experiment progress
curl http://localhost:8005/orchestration/<orch_id>/results    # aggregated results
curl http://localhost:8005/orchestration/<orch_id>/reasoning  # agent reasoning trace
```

The orchestrator generates one experiment per (capacity × latency × CC) combination, each with an ID like `iperf3_40_40_100_pfifo_cubic_a2d6e73d`.

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

### CTP replay PNAT
Background cross-traffic is replayed by the substrate worker via `tcpreplay-edit --pnat=…`. The default rule sends replayed packets to **`172.16.1.20`** — distinct from the application's interface IP (`172.16.1.1`) — so a captured PCAP can be split between application traffic and replayed cross-traffic by IP.

Override per experiment: set `replay_pnat_ip` on `GeneratedExperiment` (a single target IP; the standard source subnets `169.231.0.0/16` and `128.111.0.0/16` are reused).
Override globally: set `SUBSTRATE_REPLAY_PNAT` to a full rewrite rule.

Details and resolution order: [`services/orchestration/README.md` § CTP Replay & PNAT](services/orchestration/README.md#ctp-replay--pnat).

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
make build              # all Docker images
make up                 # start stack
make test               # run full suite via docker-compose.test.yml
make test-local         # repo-level pytest

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
