# Agentic Thin Waist

A service-oriented platform for bottleneck-centric network data generation, enabling researchers to specify experimental intents in natural language and execute reproducible, large-scale experiments across diverse infrastructure.

## Vision

Progress in networking research depends on access to data that captures how applications and protocols respond to diverse, time-varying bottleneck regimes. Yet generating such data systematically remains hard: bottleneck dynamics are simultaneously behavior-defining and execution-dependent, making them difficult to replicate, vary, or reuse across environments.

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
            |  Orchestration    (Claude + OpenClaw)     |
            |  NetForge Service                         |
            |    ├─ Intent: Link(), Bottleneck()        |
            |    ├─ Representation: CrossTraffic(), CTPs|
            |    └─ Execution: tc, tshark, tcpreplay    |
            |  NetGent Service  (application workflows) |
            |  Telemetry Service  (telemetry + results)   |
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

The architecture is guided by the principle of **progressive disaggregation**, developed across our prior systems. Each system addresses a specific form of disaggregation:

**netUnicorn** established two foundational capabilities for network data collection: (1) decoupling data-collection intents from mechanisms — expressing *what* to collect separately from *how* to realize it — and (2) disaggregating intents into independent, reusable tasks. Its service-oriented architecture (client, core/mediation, deployment services, execution services, datastore) demonstrated that this disaggregation enables portability across heterogeneous infrastructure.

**NetForge/NetReplica** applies progressive disaggregation to bottleneck-centric data generation along three dimensions:

1. **Intent–execution disaggregation**: Separates *what* bottleneck behavior to exercise from *where* and *how* it is realized. NetForge introduces a first-class *bottleneck-regime specification* — a declarative description independent of any particular testbed, cloud platform, deployment, or trace.

2. **Static–dynamic attribute disaggregation**: Separates a bottleneck regime into two independently controllable components: *static bottleneck attributes* (capacity, base latency, buffering, queue management) that define the structural envelope, and *dynamic congestion pressure* that drives time-varying contention against that structure.

3. **Trace–context disaggregation**: Disaggregates observed traffic dynamics from their original trace context via *Cross-Traffic Profiles (CTPs)*. CTPs encode the temporal structure of aggregate demand at a bottleneck — intensity, burstiness, heterogeneity, and temporal correlations — without binding to the particular path, applications, or users that produced it.

**BQT+** addresses the disaggregation of workflow specification from execution for web-based measurement. It models ISP consumer-facing interfaces as interaction state spaces, formalized as a nondeterministic finite automaton (NFA), where states correspond to observable interface conditions and transitions encode permissible user interactions. This separates querying intent from execution and enables robust, extensible operation across hundreds of heterogeneous providers.

**NetGent** extends BQT+'s NFA-based abstraction to general application workflows (YouTube, Netflix, Zoom, etc.), compiling natural-language workflow specifications into executable state machines.

Together, these systems form the building blocks of the thin waist platform.

## Architecture

### Service Structure

The platform is organized around a **NetForge Service** that maps directly to the three logical planes from the NetForge paper, plus supporting services for application execution, storage, and orchestration.

```
  CONTROL PLANE                          DATA PLANE
  (researcher's machine or SNL server)   (wherever experiments run)
 ┌──────────────────────────────┐       ┌──────────────────────────┐
 │                              │       │                          │
 │  Orchestration (Claude +     │ specs │  Substrate Workers       │
 │    OpenClaw)                 │──────→│  (tc, tshark, tcpreplay) │
 │                              │       │                          │
 │  NetForge Service            │       │  NetGent Browser Workers │
 │  ├─ Experiment API :8000     │       │  (app workflows)         │
 │  │  (intent plane)           │       │                          │
 │  ├─ CTP Service :8001        │results│  Telemetry Collectors    │
 │  │  (representation plane)   │←──────│  (pcap, tcp-info)        │
 │  └─ Substrate Worker :8002   │       │                          │
 │     (execution plane)        │       └──────────────────────────┘
 │                              │
 │  NetGent Service :8003       │
 │  Telemetry Service :8004       │
 └──────────────────────────────┘
```

The **Control Plane** runs on the researcher's machine or an SNL server — it orchestrates experiments and aggregates results. The **Data Plane** runs on infrastructure where experiments execute (can be the same machine or remote hosts).

### NetForge Service

The NetForge Service is the core of the platform, implementing NetForge's three-plane disaggregation:

**Intent Plane (Experiment API, port 8000)**: Accepts bottleneck-regime specifications via `Link()` and `Bottleneck()` objects that define static attributes (capacity, base latency, buffering/AQM) independently of any execution context. Orchestrates the CTP Service and Substrate Worker.

**Representation Plane (CTP Service, port 8001)**: Manages Cross-Traffic Profiles — reusable representations of dynamic congestion pressure extracted from production packet traces. Supports CTP operations: `extract()`, `select()`, `transform()`, `merge()`, `replay()`. Stores and indexes CTPs by statistical descriptors (intensity, burstiness, heterogeneity).

**Execution Plane (Substrate Worker, port 8002)**: Instantiates bottleneck-regime specifications on concrete infrastructure using Linux traffic control (`tc`), `tshark` for capture, and `tcpreplay` for CTP replay. Verifies that configured shaping matches intended specification.

### Supporting Services

**NetGent Service (port 8003)**: Application workflow service for browser and shell tasks. It persists natural-language workflow specs, generates executable workflows asynchronously, and runs them via job-based `generate -> execute -> result` APIs.

**Telemetry Service (port 8004)**: Telemetry storage and results query interface. Tags measurements with contextual metadata (static config, dynamic CTP, application, transport) to enable rich queries across experimental dimensions.

**Orchestration (port 8005)**: Claude + OpenClaw integration for natural-language intent interpretation. Translates researcher goals into experiment specifications, coordinates multi-step experimental campaigns, and supports the hypothesis → experimentation → analysis → refinement loop.

### Service Directory

| Service | Port | Deliverable | NetForge Plane | Lead |
|---------|------|-------------|----------------|------|
| Experiment API | 8000 | D1 | Intent | Jaber, Satyam, Snithik |
| CTP Service | 8001 | D1 | Representation | Jaber, Satyam, Snithik |
| Substrate Worker | 8002 | D1 | Execution | Jaber, Satyam, Snithik |
| NetGent Service | 8003 | D2 | Application | Eugene + Jaber |
| Telemetry Service | 8004 | D3 | Data Persistence | Manni |
| Orchestration | 8005 | D5 | Agentic | Haarika |

## Deliverables

### D1: NetForge Service — NetReplica as SOA (PRIORITY: CRITICAL)
**Lead**: Jaber | **Supporting**: Satyam, Snithik | **Start**: `services/experiment-api/README.md`

Refactor NetReplica's monolithic `controller.py` into three services mapping to NetForge's three planes. The Experiment API orchestrates CTP Service and Substrate Worker. An experiment can be created, executed on a local machine with bottleneck emulation via `docker compose up`, and telemetry collected — all from a single API call.

**Key constraint**: Jaber pursues two parallel tracks. Track A (research priority): refactor the monolith with clean dataclasses, typed interfaces, and structured output. Track B (engineering): scaffold the three-service SOA from the same dataclass contracts. The contracts are identical — convergence is mechanical.

### D2: NetGent Programmatic API (PRIORITY: HIGH)
**Lead**: Eugene + Jaber | **Start**: `services/netgent-service/README.md`

Expose NetGent's workflow engine as a programmatic API that agents can call. The current service contract is asynchronous and job-based: create a workflow with `POST /workflows/generate`, run it with `POST /workflows/execute`, and poll `GET /workflows/result/{job_id}` for both phases.

### D3: Telemetry and Storage Pipeline (PRIORITY: HIGH)
**Lead**: Manni | **Start**: `services/telemetry-service/README.md`

Build the data backbone: collect, tag, store, query. Every experiment result is tagged with its full context (static bottleneck config, dynamic CTP, application, transport protocol). Enables queries like: "Show me YouTube QoE under all CUBIC flows across capacity 10–50 Mbps."

### D4: Evaluation Pipeline (PRIORITY: STRETCH)
Automated evaluation of generated datasets against production baselines. Stretch goal that ramps up after D1–D3 integration.

### D5: Agentic Orchestration — OpenClaw + Claude (PRIORITY: VERY CRITICAL)
**Lead**: Haarika | **Start**: `services/orchestration/README.md`

The agentic interface is what makes the thin waist actually usable. Natural-language experiment specification, tool/skill declarations for all services, multi-step reasoning about network conditions and applications. Ramps up after NSDI camera-ready.

## Development Timeline (4 Weeks)

Three independent tracks running in parallel. Phase 1 (weeks 1–2) is independent work against mocked interfaces. Phase 2 (weeks 3–4) is integration. No one should be blocked by anyone else for the first two weeks.

### Weeks 1–2: Independent Development

| Track | Owner | Work |
|-------|-------|------|
| **NetForge Service** | Jaber, Satyam, Snithik | Track A: dataclasses, typed interfaces, `run_experiment()`. Track B: three-service SOA scaffold with mocked CTP and substrate |
| **NetGent API** | Eugene + Jaber | Job-based workflow API, browser/shell execution integration, TOOLS.md for OpenClaw |
| **Telemetry + Storage** | Manni | Schema design, contextual tree tagging, query API with mock data |
| **Orchestration** | Haarika | OpenClaw integration, tool declarations, intent → experiment mapping (after NSDI camera-ready) |
| **Architecture + CI** | Sylee | Service boundary review, Docker Compose, CI/CD, testing infrastructure |

### Weeks 3–4: Integration and Demo

| Track | Work |
|-------|------|
| **Service integration** | Connect NetForge Service → Telemetry Service → Orchestration |
| **End-to-end demo** | "Compare YouTube vs Zoom at 10, 25, 50 Mbps" generates experiments, executes, stores results |
| **Testing** | Integration tests across service boundaries, bottleneck state verification |
| **Documentation** | API reference, deployment guide, tutorials |

### Coordination
- Weekly Friday demo (show working software)
- Async Slack updates
- Max 1hr/week overhead — no daily standups

## Quick Start

### Prerequisites

- Docker and Docker Compose (tested on Docker 24+)
- Python 3.10+
- Git

### 1. Clone and Build

```bash
git clone git@github.com:SNL-UCSB/agentic-thin-waist.git
cd agentic-thin-waist
cp .env.example .env
make build
```

### 2. Start Services

```bash
make up
```

This starts the NetForge Service (Experiment API, CTP Service, Substrate Worker), NetGent, Telemetry, and Orchestration via Docker Compose.

### 3. Run Your First Experiment

```python
from shared.clients import ExperimentAPIClient

client = ExperimentAPIClient("http://localhost:8000")

# Specify a bottleneck regime:
# Static attributes: 10 Mbps capacity, 50ms base latency, pFIFO queue
# Dynamic attributes: select a bursty CTP from the corpus
result = client.create_experiment({
    "static": {
        "capacity_mbps": 10,
        "base_latency_ms": 50,
        "qdisc": "pfifo"
    },
    "dynamic": {
        "ctp_query": {"min_intensity": 3.0, "burstiness": "high"}
    },
    "application": "ndt",
    "duration_seconds": 30
})

print(result.status)  # "success"
print(result.metrics)  # throughput, RTT, loss measurements
```

## Directory Structure

```
agentic-thin-waist/
├── README.md                          # This file
├── docker-compose.yml                 # Development deployment
├── docker-compose.cloud.yml           # Cloud deployment (AWS scale-out)
├── Makefile                           # Common tasks
├── .gitignore
│
├── services/                          # All services
│   ├── README.md                      # Service overview and contracts
│   ├── experiment-api/                # Intent plane (D1)
│   ├── ctp-service/                   # Representation plane (D1)
│   ├── substrate-worker/              # Execution plane (D1)
│   ├── netgent-service/               # Application workflows (D2)
│   ├── telemetry-service/             # Telemetry + results (D3)
│   └── orchestration/                 # Claude + OpenClaw (D5)
│
├── shared/                            # Shared code and contracts
│   ├── README.md
│   ├── models/                        # Dataclass definitions
│   └── clients/                       # Service client libraries
│
├── docs/                              # Documentation
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   └── DEPLOYMENT.md
│
└── tests/                             # Integration tests
    └── README.md
```

## Existing Repositories

This platform builds on and refactors code from existing SNL-UCSB projects:

- **NetReplica** (private SNL-UCSB) — Bottleneck emulation substrate. Key file: `controller.py` (being refactored into the Bottleneck Service).

- **NetGent** ([github.com/SNL-UCSB/NetGent](https://github.com/SNL-UCSB/NetGent)) — NFA-based browser automation with ~100 pre-built application workflows. Being wrapped with a programmatic API for D2.

## Key Concepts

### Bottleneck Regime

A *bottleneck regime* comprises (i) a static envelope — capacity, base latency, buffering, and queue management policy — and (ii) a time-varying congestion-pressure process that drives contention within that envelope. NetForge makes this explicit by disaggregating static and dynamic attributes into independently controllable specifications.

### Cross-Traffic Profiles (CTPs)

A *Cross-Traffic Profile* is a reusable representation of dynamic congestion pressure applied at a bottleneck. CTPs encode the temporal structure of aggregate demand — intensity, burstiness, heterogeneity, and temporal correlations — without binding to the particular path, applications, or users that produced it. CTPs are extracted from production packet traces via `extract()`, indexed by statistical descriptors, and applied at bottlenecks via `replay()`. Additional operations — `select()`, `transform()`, `merge()` — enable controlled reuse and composition across different static configurations.

### Experiment Lifecycle

1. **Intent**: Researcher expresses goal in natural language (or structured specification)
2. **Decomposition**: Orchestration maps intent to one or more bottleneck-regime specifications
3. **Static specification**: Each experiment defines Link() + Bottleneck() — capacity, latency, buffer, AQM
4. **Dynamic specification**: CTP selection — choose cross-traffic profile matching desired congestion characteristics
5. **Execution**: Substrate Worker configures tc/tshark, CTP replay drives background traffic, application runs closed-loop
6. **Collection**: Telemetry captured at multiple vantage points (upstream, downstream)
7. **Storage**: Results tagged with full context and persisted for querying

### Four Requirements (from NetForge)

The platform must simultaneously satisfy: **controllability** (independent knobs for intent, static structure, and dynamic pressure), **composability** (mix-and-match intent, structure, and pressure; select/adapt/compose), **replicability** (same specifications re-instantiate comparable regimes across runs and environments), and **fidelity** (preserve realistic queueing signals and closed-loop application–bottleneck interaction).

## References

- netUnicorn (CCS '23): Data-collection platform with hourglass design and service-oriented architecture
- NetForge (SIGCOMM submission #1035): Programmable substrate for bottleneck-centric data generation via progressive disaggregation
- BQT+ (SIGCOMM '26 submission): Robust broadband plan measurement via NFA-based interaction state spaces
- BQT (SIGCOMM '23): Broadband plan querying tool
- NetReplica: Private SNL-UCSB repository
- Linux Traffic Control (tc): [man7.org/linux/man-pages/man8/tc.8.html](https://man7.org/linux/man-pages/man8/tc.8.html)

## Team

- **PI**: Prof. Arpit Gupta (SNL-UCSB)
- **Organization**: [SNL-UCSB](https://github.com/SNL-UCSB)
- **Repository**: [github.com/SNL-UCSB/agentic-thin-waist](https://github.com/SNL-UCSB/agentic-thin-waist) (private)

## License

Proprietary — SNL-UCSB. All rights reserved.

---

**Last Updated**: 2026-03-04
**Status**: Architecture Phase — Sprint Kickoff
