# Agentic Thin Waist

An agentic infrastructure for network research data generation, enabling researchers to conduct reproducible, large-scale experiments across diverse computing environments.

## Project Vision

The **Data Generation Hourglass** is an intellectual property framework that captures the essential principles of scalable network research. The waist represents a thin, composable set of services that bridges diverse research intents (top) with diverse infrastructure (bottom):

```
                    THE DATA GENERATION HOURGLASS

    Replication | Counterfactual | Pre-training | Broadband
    Teaching    | DOE Synthesis  | Benchmarking | Hypothesis
   ─────────────────────────────────────────────────────────
          \          DIVERSE RESEARCH INTENTS            /
           \                                            /
            \   (any researcher, any question)         /
             \                                        /
              ────────────────────────────────────────
              |          AGENTIC THIN WAIST          |
              |                                      |
              |  OpenClaw + Claude  (orchestration)  |
              |  Experiment API     (intent plane)   |
              |  CTP Service        (representation) |
              |  NetGent            (app execution)  |
              |  Storage Service    (telemetry)      |
              |  Substrate Worker   (network exec)   |
              |                                      |
              ────────────────────────────────────────
             /                                        \
            /    (any Docker-capable host)              \
           /                                            \
          /          DIVERSE INFRASTRUCTURE              \
   ─────────────────────────────────────────────────────────
    Laptop Docker | AWS EC2 | PINOT Campus | ANL/ESnet
    Mininet       | Azure   | SNL Servers  | NetUnicorn
```

**Key principle**: Researchers specify research intents (top), agents orchestrate execution (waist), and infrastructure adapts to environment (bottom). The Thin Waist services are infrastructure-agnostic and can run on any Docker-capable host.

## Progressive Disaggregation

This architecture is built on the principle of **progressive disaggregation**, where each generation of tools builds upon and refactors previous work:

- **NetUnicorn** (monolithic framework) → network orchestration, data collection
- **NetReplica** (bottleneck emulation) → CTP service refactoring (tc, tshark integration)
- **NetForge** (experiment specification) → CTP algebra, representation plane
- **NetGent** (agentic browser automation) → NFA-based workflow execution, application plane
- **BQT+** (data storage and analysis) → storage service, telemetry aggregation
- **Thin Waist** (agentic orchestration) → OpenClaw + Claude, intent plane, end-to-end workflow

Each layer preserves the IP and APIs of previous work while refactoring internals for clarity and composability.

## Architecture Overview

### The Thin Waist Services

The Agentic Thin Waist consists of six tightly coupled services that form the critical infrastructure layer:

#### Control Plane vs Data Plane

```
  CONTROL PLANE                          DATA PLANE
  (user's machine or SNL server)         (wherever data is generated)
 ┌──────────────────────────┐           ┌──────────────────────────┐
 │                          │           │                          │
 │  OpenClaw + Claude       │  dispatch │  Substrate Worker(s)     │
 │  (intent → experiment)   │─────────→ │  (tc, tshark, tcpreplay) │
 │                          │           │                          │
 │  Experiment API :8000    │           │  NetGent Browser Workers │
 │  (orchestration)         │           │  (Netflix, YouTube, Zoom)│
 │                          │           │                          │
 │  CTP Service :8001       │  results  │  Telemetry Collectors    │
 │  (CTP algebra)           │ ←──────── │  (pcap, transport state) │
 │                          │           │                          │
 │  Storage Service :8004   │           │                          │
 │  (results DB, queries)   │           │                          │
 │                          │           │                          │
 │  NetGent NFA Compiler    │           │                          │
 └──────────────────────────┘           └──────────────────────────┘
```

The **Control Plane** runs on the researcher's machine or SNL server, orchestrating experiments and aggregating results. The **Data Plane** runs on infrastructure where experiments are executed (could be the same machine or remote infrastructure).

#### Service Interaction Flow

```
  "Compare YouTube vs Zoom at 10, 25, 50 Mbps"
                    │
                    ▼
        ┌───────────────────────┐
        │  Claude + OpenClaw    │  D5: intent → experiment JSON
        │  (port 8005)          │
        └───────────┬───────────┘
                    │ POST /experiments
                    ▼
        ┌───────────────────────┐
        │  Experiment API       │  D1: orchestrates everything
        │  (port 8000)          │
        └──┬────────┬────────┬──┘
           │        │        │
           ▼        ▼        ▼
     ┌─────────┐ ┌────────┐ ┌─────────┐
     │ CTP     │ │Substrate│ │ NetGent │
     │ Service │ │ Worker │ │ Service │
     │ :8001   │ │ :8002  │ │ :8003   │
     └────┬────┘ └───┬────┘ └────┬────┘
          │          │           │
          └──────────┼───────────┘
                     │ results + telemetry
                     ▼
        ┌───────────────────────┐
        │  Storage Service      │  D3: store, tag, query
        │  (port 8004)          │
        └───────────────────────┘
```

### Service Directory

| Service | Port | D# | Purpose | Status |
|---------|------|----|---------|----|
| **Experiment API** | 8000 | D1 | Orchestration, experiment lifecycle | Intent Plane |
| **CTP Service** | 8001 | D1 | Network capacity/latency emulation | Representation Plane |
| **Substrate Worker** | 8002 | D1 | Execute network conditions (tc, tshark) | Execution Plane |
| **NetGent Service** | 8003 | D2 | Browser automation, application workflows | Application Execution |
| **Storage Service** | 8004 | D3 | Telemetry storage, results query, tagging | Data Persistence |
| **Orchestration** | 8005 | D5 | Claude + OpenClaw, intent interpretation | Agentic Orchestration |

## Deliverables Overview

### D1: Network Virtualization Substrate (PRIORITY: CRITICAL)
**Status**: Foundation layer for all other work
- Experiment API: orchestration, state machine, lifecycle
- CTP Service: capacity/latency profiles, CTP algebra
- Substrate Worker: tc/tshark integration, network state verification

**Testing**: An experiment can be created, executed on a local machine with bottleneck emulation, and telemetry collected.

### D2: Application Execution Layer (PRIORITY: HIGH)
**Status**: Browser automation and application-level workflows
- NetGent Service: NFA-based workflow execution
- Workflow compiler: convert workflows to executable specs
- Integration with substrate worker for QoE metrics collection

**Testing**: YouTube video playback under various network conditions produces consistent QoE metrics.

### D3: Telemetry and Results Storage (PRIORITY: HIGH)
**Status**: Centralized storage and query interface
- Storage Service: time-series DB for measurements
- Query API: filter by experiment, application, network condition
- Contextual tree tagging: link results to experiment metadata

**Testing**: Results from D1 and D2 are persistently stored and retrievable.

### D4: Distributed Execution (PRIORITY: MEDIUM)
**Status**: Multi-host coordination
- Kubernetes manifests for multi-node deployment
- Remote substrate worker provisioning
- Load balancing and fault recovery

**Testing**: Experiments can run on SNL infrastructure without local Docker.

### D5: Agentic Orchestration (PRIORITY: MEDIUM)
**Status**: Claude + OpenClaw for intent interpretation
- Natural language experiment specification
- Tool/Skill declarations for all services
- Multi-step reasoning about network conditions and applications

**Testing**: "Compare YouTube vs Zoom at 10, 25, 50 Mbps" generates and executes appropriate experiments.

## Quick-Start Guide

### Prerequisites

- Docker and Docker Compose (tested on Docker 24+)
- Python 3.10+
- Git

### 1. Clone and Build

```bash
git clone git@github.com:SNL-UCSB/agentic-thin-waist.git
cd agentic-thin-waist
make build
```

### 2. Start Services

```bash
make up
```

This starts all services in Docker Compose (development mode):
- Experiment API on http://localhost:8000
- CTP Service on http://localhost:8001
- Substrate Worker on http://localhost:8002
- NetGent Service on http://localhost:8003
- Storage Service on http://localhost:8004
- Orchestration on http://localhost:8005

### 3. Run Your First Experiment

```bash
# Create a simple experiment (10 Mbps capacity, 50ms latency)
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": "test-001",
    "capacity_mbps": 10,
    "latency_ms": 50,
    "application": "youtube",
    "duration_seconds": 30,
    "num_trials": 1
  }'

# Check experiment status
curl http://localhost:8000/experiments/test-001

# Query results
curl "http://localhost:8004/results?experiment_id=test-001"
```

### 4. Using the Agentic Interface

```bash
# Query Claude via OpenClaw orchestration
curl -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency"
  }'
```

## Directory Structure

```
agentic-thin-waist/
├── README.md                          # This file
├── docker-compose.yml                 # Development compose
├── docker-compose.cloud.yml           # Cloud deployment compose
├── Makefile                           # Common tasks
├── .gitignore
│
├── services/                          # All microservices
│   ├── README.md                      # Service overview
│   ├── experiment-api/                # D1: Orchestration
│   ├── ctp-service/                   # D1: Network emulation
│   ├── substrate-worker/              # D1: Execution
│   ├── netgent-service/               # D2: Application automation
│   ├── storage-service/               # D3: Data persistence
│   └── orchestration/                 # D5: Agentic orchestration
│
├── shared/                            # Shared code and contracts
│   ├── README.md
│   ├── models/                        # Dataclass definitions
│   └── clients/                       # HTTP client utilities
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

## Key Concepts

### The Contextual Tree

Every experiment result includes a **Contextual Tree** that tags measurements with their context:

```python
@dataclass
class ContextualTreeNode:
    c_static: dict      # Capacity, latency, buffer, AQM (static config)
    c_dyn: dict         # CTP cluster ID, description (dynamic network state)
    c_app: dict         # Application name, workflow spec
    c_trans: dict       # Transport protocol, congestion control
```

This enables rich queries: "Show me YouTube performance under all CUBIC flows across capacity 10-50 Mbps."

### CTP: Capacity-Throughput Profile

A **CTP** is a tuple `(capacity_mbps, latency_ms, loss_rate, aqm_policy)` that describes network conditions. The CTP Service translates these into Linux `tc` (traffic control) commands on the data plane.

### Experiment Lifecycle

1. **Intent** (Claude) → researcher's goal in natural language
2. **Specification** (OpenClaw) → experiment JSON with explicit parameters
3. **Provisioning** (Experiment API) → allocate resources, verify substrate
4. **Execution** (CTP + Substrate + NetGent) → run workflows, collect telemetry
5. **Aggregation** (Storage Service) → persist results, tag with context
6. **Analysis** (Researcher) → query, visualize, interpret

## Existing Repositories

The Agentic Thin Waist builds on and refactors code from existing SNL-UCSB projects:

- **NetReplica** (`github.com/SNL-UCSB/netReplica`) — bottleneck emulation, tc integration
  - Key files: `controller.py` (needs refactoring into CTP Service)
  - Reference: https://github.com/SNL-UCSB/netReplica

- **NetGent** (private SNL-UCSB repo) — NFA-based browser automation
  - ~100 pre-built workflows (YouTube, Netflix, Zoom, Twitch, etc.)
  - Reference: Will be integrated as D2 implementation

- **OpenClaw** — orchestration framework for agentic systems
  - Tool and Skill declarations for multi-step reasoning
  - Reference: To be integrated as D5 implementation

- **BQT+** — data storage and analysis (private SNL-UCSB)
  - Time-series database design, query optimization
  - Reference: Will inform D3 Storage Service design

## Development Timeline

### Week 1: Foundation (D1 Core)
- Experiment API: REST endpoints, experiment state machine
- CTP Service: capacity/latency algebra, tc integration
- Substrate Worker: container setup, Linux capability management
- Tests: Basic experiment lifecycle

### Week 2: Integration (D1 Complete)
- Service-to-service API contracts finalized
- Docker Compose development environment
- Integration tests: full experiment execution
- Bottleneck state verification (measured vs configured)

### Week 3: Application Layer (D2 Start)
- NetGent Service API design
- NFA workflow compiler integration
- QoE metrics collection from browsers
- D2 partial completion: YouTube/Zoom basic workflows

### Week 4: Storage and Analytics (D3)
- Storage Service schema design
- Contextual tree tagging on results
- Query API: experiment filter, time-range, tags
- Results visualization dashboard

### Week 5: Agentic Orchestration (D5 Start)
- OpenClaw integration
- Tool declarations for all services
- Claude prompt engineering for intent → experiment mapping
- D5 partial completion: basic intent interpretation

### Week 6: Distributed and Deployment (D4 + Polish)
- Kubernetes manifests for SNL deployment
- Multi-host Substrate Worker provisioning
- Cloud deployment (AWS/Azure) via docker-compose.cloud.yml
- Documentation and tutorials

### Week 7-8: Refinement and Testing
- Comprehensive test suite
- Performance optimization
- Documentation updates
- D2, D4, D5 completion and testing

## Team and Contacts

- **Project Lead**: Prof. Guido Appenzeller
- **Organization**: SNL-UCSB (github.com/SNL-UCSB)
- **Repository**: github.com/SNL-UCSB/agentic-thin-waist (private)

## References

- NetUnicorn: https://github.com/Aritro-BhumitraX/NetUnicorn
- NetReplica: https://github.com/SNL-UCSB/netReplica
- Traffic Control (tc): https://man7.org/linux/man-pages/man8/tc.8.html
- tcpdump/tshark: https://www.tcpdump.org/
- Docker Compose: https://docs.docker.com/compose/
- OpenClaw: [Internal SNL-UCSB documentation]

## License

Proprietary - SNL-UCSB. All rights reserved.

---

**Last Updated**: 2026-03-04
**Status**: Architecture Phase
**Next Milestone**: D1 Deliverables (Week 2)
