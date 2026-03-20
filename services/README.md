# Agentic Thin Waist: Services Architecture

This document provides a quick reference for the six microservices comprising the Agentic Thin Waist platform, organized by the three logical planes: Intent plane, Representation plane, and Execution plane. Services operate in parallel over a 4-week timeline: weeks 1-2 with mocked interfaces, weeks 3-4 for integration.

## MVP Goal

**Intent → Data in 4 weeks.** A researcher expresses a data generation intent in natural language. The system translates it into experiment specifications, configures infrastructure, executes the experiment, and stores the resulting data. The researcher specifies the intent and gets the data — without dealing with any of the mechanics in between. Intelligence, analysis, and the closed-loop feedback cycle (generate → analyze → refine intent → regenerate) are post-MVP extensions.

## Terminology: Experiments and Iterations

An **experiment** is a research campaign encompassing one or more **iterations**. Each iteration is an atomic run: one network configuration (NetReplica) paired with one or more concurrent application configurations (NetGent). A single iteration can run multiple applications simultaneously on the same bottleneck — for example, YouTube and Zoom competing for a shared 10 Mbps link. The Experiment API operates at the iteration level. The Orchestration Service operates at the experiment level — synthesizing iterations from a research intent.

**Composition within and across iterations:**

| Pattern | Scope | Description | Example |
|---------|-------|-------------|---------|
| **Single-app** | Within iteration | One network condition, one application | YouTube alone at 10 Mbps / 50ms |
| **Multi-app concurrent** | Within iteration | One network condition, multiple applications running simultaneously | YouTube + Zoom sharing 10 Mbps / 50ms |
| **Parameter sweep** | Across iterations | One app config across multiple network conditions | YouTube at 10 / 25 / 50 Mbps (3 iterations) |
| **Full Cartesian** | Across iterations | Multiple app combinations × multiple network conditions | {YouTube-only, Zoom-only, YouTube+Zoom} × {10, 25, 50 Mbps} = 9 iterations |

The multi-app concurrent pattern is key: running applications simultaneously within one iteration captures cross-application interference effects (bandwidth competition, queue sharing) that separate iterations cannot.

## Architecture Overview: Three Logical Planes

Progressive disaggregation of the Agentic Thin Waist spans three dimensions:
1. **Intent–Execution**: Intent plane (high-level research goals) → Execution plane (low-level kernel operations)
2. **Static–Dynamic**: Static bottleneck attributes (capacity, latency) → Dynamic congestion pressure
3. **Trace–Context**: Individual packet traces (pcap) → Contextual trees with metadata

The three logical planes are:

| Plane | Services | Responsibility | Ports |
|-------|----------|-----------------|-------|
| **Intent plane** | Experiment API, Orchestration | Accept research intent; generate experiment specs; coordinate execution sequencing and synchronization | 8000, 8005 |
| **Representation plane** | CTP Service, Telemetry Service | Define and compose Cross-Traffic Profiles (CTPs); store and query experiment results with contextual metadata | 8001, 8004 |
| **Execution plane** | Substrate Worker, NetGent | Execute bottleneck conditions; apply CTP traffic via tcpreplay; run application workflows | 8002, 8003 |

## Service Registry

| Service | Port | Deliverable | Owner(s) | Dependencies |
|---------|------|-------------|----------|--------------|
| Experiment API | 8000 | D1 (CRITICAL) | Jaber, Satyam, Snithik | All services |
| CTP Service | 8001 | D1 (CRITICAL) | Jaber, Satyam, Snithik | None |
| Substrate Worker | 8002 | D1 (CRITICAL) | Jaber, Satyam, Snithik | CTP Service (replay PCAP) |
| NetGent Service | 8003 | D2 (HIGH) | Eugene + Jaber | None (receives spec from upper layer) |
| Telemetry Service | 8004 | D3 (HIGH) | Manni | None |
| Orchestration Service | 8005 | D5 (VERY CRITICAL) | Haarika | All services |

**Team**: Prof. Arpit Gupta (PI); Students: Jaber, Haarika, Manni, Eugene, Sylee.

**Timeline**: 4 weeks parallel. Weeks 1-2: independent development against mocked interfaces. Weeks 3-4: integration.

### Design Principle: Dumb Services, Smart Controller

Each downstream service (CTP, Substrate Worker, NetGent, Telemetry) is **narrow and stateless with respect to coordination**. A service receives one configuration at a time, executes it, and returns a result. It does not track which iteration it is on, how many remain, or what other services are doing. All coordination, sequencing, progress tracking, retry logic, and cross-service awareness lives in the **Experiment API (controller)**.

For an experiment with 100 iterations, the controller dispatches iteration configs one at a time (or in controlled batches). Each service sees only its current task. This keeps services simple, testable, and independently deployable.

### Design Principle: No Direct Coupling Between NetGent and Telemetry

NetGent (application workflows) and the Telemetry Service (result storage) do **not** communicate directly. The upper layer (Experiment API or Orchestration) provides independent specifications to each:

- **NetGent** receives a workflow spec that includes instrumentation requirements (e.g., "enable Stats for Nerds" for YouTube, "capture HAR file"). NetGent's job is to execute the workflow and produce artifacts — it does not know or care where they are stored.
- **Telemetry Service** receives experiment results and artifacts from the Experiment API after execution completes. It stores, tags, and indexes them — it does not know which application generated them.

This separation means the Experiment API is responsible for specifying both (a) the NetGent workflow with correct instrumentation flags and (b) the Telemetry Service storage request with correct contextual metadata. Neither downstream service needs awareness of the other.

---

## Intent Plane: Experiment API & Orchestration

### 1. Experiment API (Port 8000) — D1 CRITICAL

**Location**: `./experiment-api/`

**Purpose**: Central control point implementing the intent plane. Manages experiment lifecycle and coordinates all downstream services.

**Responsibilities**:
- Create and manage experiment specifications
- Coordinate CTP validation, substrate configuration, and application execution
- Implement experiment state machine
- Verify bottleneck regime before workflow execution
- Aggregate results from Substrate Worker, NetGent Service, and Telemetry Service

**Key Endpoints**:
- `POST /experiments` — Create new experiment
- `GET /experiments/{experiment_id}` — Retrieve experiment status
- `GET /experiments` — List experiments with filtering
- `POST /experiments/{experiment_id}/execute` — Trigger execution pipeline
- `GET /experiments/{experiment_id}/results` — Fetch aggregated results

**Core Contracts**:
- Input: Experiment with capacity_mbps, latency_ms, loss_rate, applications (one or more concurrent), duration
- Output: ExperimentResult with bottleneck_state, qoe_metrics, pcap_paths, contextual_tree

**Dependencies**: Experiment API depends on all downstream services.

**Implementation**:
1. Flask/FastAPI REST server
2. Experiment state machine: pending → provisioning → running → complete → archived
3. HTTP clients for all services with timeout/retry logic
4. Request validation using Pydantic
5. Result aggregation from all contributors
6. Integration tests covering full pipeline

---

### 6. Orchestration Service (Port 8005) — D5 VERY CRITICAL

**Location**: `./orchestration/`

**Purpose**: Agentic orchestration translating natural language research intent into structured experiment specifications using Claude and OpenClaw.

**Responsibilities**:
- Accept natural language research intents
- Reason about network conditions and application characteristics using Claude
- Declare tool/skill contracts for all services via OpenClaw
- Generate valid Experiment JSON specifications
- Dispatch to Experiment API; manage multi-step reasoning

**Key Endpoints**:
- `POST /intent` — Submit research intent in natural language
- `GET /status/{request_id}` — Check orchestration completion status
- `GET /tools` — List OpenClaw tool declarations
- `GET /skills` — List OpenClaw skill definitions

**Configuration Files**:
- `TOOLS.md` — OpenClaw declarations: Experiment API, CTP Service, Telemetry Service endpoints
- `SKILLS.md` — OpenClaw skill definitions for multi-step workflows (e.g., "compare applications across bandwidth range")
- `prompts/system.md` — System prompt for Claude
- `prompts/examples.md` — Few-shot examples for intent → experiment mapping

**Core Contracts**:
- Input: ResearchIntent (natural language text + optional context/preferences)
- Output: GeneratedExperiment list with capacity_mbps, latency_ms, application, duration, reasoning

**Dependencies**: All services (via HTTP).

**Implementation**:
1. Claude API integration (Anthropic SDK)
2. OpenClaw tool/skill system
3. Prompt templates for intent understanding
4. HTTP client for Experiment API
5. Request logging and Claude reasoning capture
6. Few-shot examples in prompts/
7. Graceful error recovery for malformed intents
8. Validation that experiments are within reasonable bounds

---

## Representation Plane: CTP Service & Telemetry Service

### 2. CTP Service (Port 8001) — D1 CRITICAL

**Location**: `./ctp-service/`

**Purpose**: The representation plane defines Cross-Traffic Profiles (CTPs) and their algebra. CTPs abstract network conditions into composable units: capacity (Mbps), latency (ms), loss rate, and AQM policy.

**Responsibilities**:
- Define CTP profiles with static bottleneck attributes (capacity, latency, loss_rate, aqm_policy)
- Implement CTP operations: extract(), select(), transform(), merge()
- Export replay-ready PCAP data for Substrate Worker
- Support CTP composition and algebra
- Provide cluster-based CTP selection: CTPs are grouped into clusters with semantically meaningful attributes (intensity, burstiness, temporal correlation). The Orchestration Service can query by cluster attributes (e.g., "high-burstiness clusters") or by cluster ID. Cluster taxonomy is derived from preprocessing of production traces.
- Verify network state matches configured CTP

**Key Endpoints**:
- `POST /ctps/validate` — Validate CTP specification
- `POST /ctps/compile` — Compile CTP to tc qdisc commands
- `GET /ctps/presets` — List preset CTP profiles
- `POST /ctps/verify` — Verify network matches CTP (within 5% tolerance)

**Core Contracts**:
```python
@dataclass
class CTP:
    capacity_mbps: float
    latency_ms: float
    loss_rate: float
    aqm_policy: str  # "fifo", "codel", "pie", "fq_codel"

@dataclass
class BottleneckRegime:
    static_attrs: dict  # capacity, latency, loss, aqm
    dynamic_pressure: dict  # measured_throughput, measured_rtt, queue_depth
```

**Dependencies**: None (independent service).

**Implementation**:
1. CTP dataclass definitions with validation
2. tc command generator for each AQM policy
3. Network measurement: iperf3 for throughput, ping for RTT
4. CTP operations: extract, select, transform, merge
5. Physical limit validation

---

### 5. Telemetry Service (Port 8004) — D3 HIGH

**Location**: `./telemetry-service/`

**Purpose**: Representation plane data layer. Stores experiment results with contextual tree metadata spanning static bottleneck attributes, dynamic congestion pressure, application characteristics, and transport state. The Telemetry Service is part of the Representation plane because it defines and manages the structured representations (contextual trees) that give meaning to raw execution data.

**Responsibilities**:
- Store ExperimentResult with complete contextual tree
- Support context dimensions: c_static (capacity, latency, loss, aqm), c_dyn (measured state), c_app (application, workflow), c_trans (protocol, cc)
- Provide query API with rich filtering (experiment, application, capacity range, latency range, date range)
- Archive pcap files and workflow artifacts
- Enable reproducibility through complete context capture

**Key Endpoints**:
- `POST /results` — Store experiment result with contextual tree
- `GET /results` — Query results with filters
- `GET /results/{result_id}` — Retrieve single result
- `POST /artifacts/{artifact_id}/upload` — Store pcap or artifact
- `GET /artifacts/{artifact_id}` — Retrieve artifact
- `POST /tags` — Tag results with custom metadata

**Core Contracts**:
```python
@dataclass
class ContextualTree:
    c_static: dict  # capacity_mbps, latency_ms, loss_rate, aqm_policy
    c_dyn: dict  # measured_throughput, measured_rtt, queue_depth
    c_app: dict  # application_name, workflow_spec, workflow_id
    c_trans: dict  # protocol, congestion_control, cc_algorithm

@dataclass
class ExperimentResult:
    experiment_id: str
    bottleneck_state: dict  # static + dynamic
    qoe_metrics: dict
    pcap_paths: List[str]
    contextual_tree: ContextualTree
    timestamp: str
```

**Dependencies**: None (independent data layer).

**Implementation**:
1. Database setup (SQLite dev, PostgreSQL production)
2. SQLAlchemy ORM for results, artifacts, tags
3. REST CRUD endpoints
4. Query builder with multi-field filtering
5. File upload/download for pcaps and artifacts
6. Contextual tree storage and indexing
7. Migration scripts

---

## Execution Plane: Substrate Worker & NetGent

### 3. Substrate Worker (Port 8002) — D1 CRITICAL

**Location**: `./substrate-worker/`

**Purpose**: Data plane execution. Applies bottleneck regime conditions to the network using Linux kernel capabilities, replays CTP traffic via tcpreplay, and collects packet traces and telemetry.

**Responsibilities**:
- Apply CTP configurations via tc qdisc management
- Replay CTP traffic via tcpreplay (receives replay-ready PCAP from CTP Service)
- Collect packet traces via tshark or tcpdump
- Measure dynamic bottleneck state (throughput, RTT, congestion pressure)
- Execute privileged network operations (requires CAP_NET_ADMIN)
- Store raw pcap files for trace-level analysis

**Key Endpoints**:
- `POST /workers/configure` — Apply CTP to network interface
- `GET /workers/status` — Get current bottleneck regime
- `POST /workers/capture/start` — Start packet capture (tshark)
- `POST /workers/capture/stop` — Stop capture, return pcap file path
- `GET /workers/metrics` — Get measured throughput/RTT/queue_depth
- `POST /workers/replay` — Replay CTP traffic via tcpreplay

**Core Contracts**:
```python
@dataclass
class BottleneckRegime:
    static_attrs: dict  # configured capacity, latency, loss, aqm
    dynamic_pressure: dict  # measured_throughput, measured_rtt

@dataclass
class TelemetrySnapshot:
    timestamp: str
    interface: str
    tx_packets: int
    rx_packets: int
    tx_bytes: int
    rx_bytes: int
    packet_loss_percent: float
```

**Dependencies**: CTP Service (for replay-ready PCAP data).

**Implementation**:
1. Flask server with privileged mode support (CAP_NET_ADMIN)
2. tc command executor for qdisc management
3. tcpreplay for CTP traffic replay (receives PCAP from CTP Service)
4. tshark/tcpdump integration for packet capture
5. iperf3 client for throughput measurement
6. ping-based RTT measurement
7. Pcap storage to mounted volume
8. Linux sysctl tuning

---

### 4. NetGent Service (Port 8003) — D2 HIGH

**Location**: `./netgent-service/`

**Purpose**: Application-level execution plane. Executes application workflows — both browser-based (YouTube, Netflix, Zoom via NFA/Selenium) and host-level processes (ping, speed tests, shell commands) — generating application-specific traffic and measuring QoE.

**Responsibilities**:
- Compile NetGent workflows from NFA specification (browser-based applications)
- Execute browser automation (YouTube, Netflix, Zoom, etc.)
- Execute host-level processes (ping, NDT speed tests, iperf3, shell commands)
- Collect QoE metrics: video startup time, rebuffer events, bitrate
- Maintain an **active application registry**: the authoritative list of supported applications
- Store workflow logs and artifacts

**Key Endpoints**:
- `POST /workflows/compile` — Compile NFA from spec
- `POST /workflows/generate` — Run workflow under current network conditions
- `GET /workflows/results/{workflow_id}` — Retrieve execution results
- `GET /workflows/available` — List available NFA workflows
- `POST /workflows/qoe/measure` — Extract QoE metrics from logs

**Core Contracts**:
```python
@dataclass
class WorkflowResult:
    workflow_id: str
    application: str  # "youtube", "netflix", "zoom"
    status: str  # "success", "failure", "timeout"
    states_executed: List[str]
    qoe_metrics: dict  # startup_time_ms, rebuffer_events, bitrate
    duration_seconds: float

@dataclass
class QoEMetrics:
    video_startup_time_ms: float
    mean_bitrate_mbps: float
    rebuffer_events: int
    rebuffer_duration_ms: float
```

**Dependencies**: Substrate Worker (network coordination). NetGent does not communicate directly with Telemetry Service; the Experiment API handles result storage.

**Implementation**:
1. NetGent NFA execution engine integration
2. NFA compiler from JSON specs
3. Selenium or Puppeteer for browser automation
4. QoE metric extractors per application
5. Workflow state logging and error handling
6. Timeout management (30-second default)
7. Artifact storage

---

## Service Interaction Flow

```
Orchestration Service (natural language intent)
    ↓
Experiment API / Controller (experiment specification + sequencing)
    │
    ├→ [Pre-flight checks]
    │   ├→ CTP Service: Is the requested CTP replay-ready? (cold start check)
    │   │   └→ If not ready: instruct CTP Service to prepare, wait for confirmation
    │   ├→ NetGent Service: Is the requested application supported? (GET /workflows/available)
    │   │   └→ If not supported: reject experiment (application onboarding is out-of-band)
    │   └→ Substrate Worker: Is the worker available?
    │
    ├→ [Per-iteration dispatch — one at a time]
    │   ├→ CTP Service (validate bottleneck regime, export replay-ready PCAP)
    │   ├→ Substrate Worker (configure bottleneck via tc)
    │   ├→ Substrate Worker (replay CTP traffic via tcpreplay, start capture)
    │   ├→ NetGent Service (execute NFA workflow, collect QoE)
    │   ├→ Substrate Worker (stop capture, measure dynamic state)
    │   └→ Telemetry Service (persist result + contextual tree)
    │
    ↓
Experiment API (aggregate and return result)
```

The Experiment API orchestrates the sequencing implicitly: it manages phase transitions (provisioning → replay_warmup → executing → collecting → complete) and infers synchronization requirements from the experiment specification's infrastructure type. The controller dispatches one iteration at a time — services never receive batch instructions or need awareness of other iterations.

**Pre-flight checks** are the controller's responsibility. Before dispatching any iteration, the controller verifies:

1. **CTP readiness (cold start)**: The controller queries the CTP Service to confirm the requested CTP is replay-ready. If the CTP requires preparation (extracting from a larger dataset, transforming, etc.), the controller instructs the CTP Service to prepare it and waits for confirmation before proceeding. This prevents iteration failures due to missing replay data.

2. **Application support (NetGent readiness)**: The controller queries NetGent's active application registry (`GET /workflows/available`) to confirm the requested application is supported. If the application is not in the registry, the experiment cannot proceed — adding new application support is a separate, out-of-band process (not part of the thin waist pipeline).

3. **Substrate availability**: The controller confirms at least one Substrate Worker is available and healthy.

Each service contributes to the final ExperimentResult:
- **CTP Service**: Validated bottleneck regime (static attributes), replay-ready PCAP export
- **Substrate Worker**: tc enforcement, CTP replay via tcpreplay, pcap capture, measured dynamic state
- **NetGent Service**: QoE metrics, workflow artifacts
- **Telemetry Service**: Persistent storage, contextual tree tagging

---

## Core Requirements

The platform is designed to satisfy four key requirements:

1. **Controllability**: CTP operations (extract, select, transform, merge) define network conditions; Substrate Worker enforces them via tc and tcpreplay
2. **Composability**: Services operate independently (weeks 1-2 with mocks) and compose (weeks 3-4 integration)
3. **Fidelity**: Substrate Worker verification ensures applied conditions match specifications within 5% tolerance
4. **Replicability**: Contextual trees capture all context; pcap traces enable offline replay

---

## MVP Deployment: Single-Node Architecture

The MVP targets a **single-node deployment**: the control plane (Experiment API, Orchestration) and data plane (Substrate Worker, NetGent) all run on the same machine via Docker Compose. This means all services share a host clock, network namespace (with appropriate bridging), and filesystem. Multi-node deployment (overlay networks, GRE tunnels, distributed testbed) is a post-MVP extension.

The control plane always runs locally (researcher's laptop or SNL server). In future multi-node configurations, only the data plane scales out to cloud/remote infrastructure.

## Development Workflow

**Weeks 1-2 (Independent Work)**:
- Each team implements services against mocked dependencies
- Use Docker Compose with mock services for local testing
- D1 services (Jaber) and D2 partial (Eugene) proceed in parallel
- D3 (Manni) implements storage with test data generators
- D5 (Haarika) builds orchestration layer with dummy service stubs

**Weeks 3-4 (Integration)**:
- Remove mocks; wire real services
- Haarika tests Orchestration → Experiment API → others
- Jaber validates full D1 pipeline with real Substrate Worker
- Eugene completes NetGent + Substrate Worker integration
- Manni validates Telemetry Service under real query load

**Testing**: Unit tests for core logic; integration tests for service chains.

---

**Last Updated**: 2026-03-07 | **Status**: Design Phase | **Next**: Week 1-2 Parallel Implementation
