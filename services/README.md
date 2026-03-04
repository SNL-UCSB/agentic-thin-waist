# Agentic Thin Waist: Services Architecture

This document provides a quick reference for the six microservices comprising the Agentic Thin Waist platform, organized by the three logical planes: Intent plane, Representation plane, and Execution plane. Services operate in parallel over a 4-week timeline: weeks 1-2 with mocked interfaces, weeks 3-4 for integration.

## Architecture Overview: Three Logical Planes

Progressive disaggregation of the Agentic Thin Waist spans three dimensions:
1. **Intent–Execution**: Intent plane (high-level research goals) → Execution plane (low-level kernel operations)
2. **Static–Dynamic**: Static bottleneck attributes (capacity, latency) → Dynamic congestion pressure
3. **Trace–Context**: Individual packet traces (pcap) → Contextual trees with metadata

The three logical planes are:

| Plane | Services | Responsibility | Ports |
|-------|----------|-----------------|-------|
| **Intent plane** | Experiment API, Orchestration | Accept research intent; generate experiment specs | 8000, 8005 |
| **Representation plane** | CTP Service | Define and compose Cross-Traffic Profiles (CTPs) | 8001 |
| **Execution plane** | Substrate Worker, NetGent, Telemetry | Execute bottleneck conditions; apply traffic patterns; collect results | 8002, 8003, 8004 |

## Service Registry

| Service | Port | Deliverable | Owner(s) | Dependencies |
|---------|------|-------------|----------|--------------|
| Experiment API | 8000 | D1 (CRITICAL) | Jaber, Satyam, Snithik | All services |
| CTP Service | 8001 | D1 (CRITICAL) | Jaber, Satyam, Snithik | None |
| Substrate Worker | 8002 | D1 (CRITICAL) | Jaber, Satyam, Snithik | Telemetry Service |
| NetGent Service | 8003 | D2 (HIGH) | Eugene + Jaber | None (receives spec from upper layer) |
| Telemetry Service | 8004 | D3 (HIGH) | Manni | None |
| Orchestration Service | 8005 | D5 (VERY CRITICAL) | Haarika | All services |

**Team**: Prof. Arpit Gupta (PI); Students: Jaber, Haarika, Manni, Eugene, Sylee.

**Timeline**: 4 weeks parallel. Weeks 1-2: independent development against mocked interfaces. Weeks 3-4: integration.

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
- Input: Experiment with capacity_mbps, latency_ms, loss_rate, application, duration
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

## Representation Plane: CTP Service

### 2. CTP Service (Port 8001) — D1 CRITICAL

**Location**: `./ctp-service/`

**Purpose**: The representation plane defines Cross-Traffic Profiles (CTPs) and their algebra. CTPs abstract network conditions into composable units: capacity (Mbps), latency (ms), loss rate, and AQM policy.

**Responsibilities**:
- Define CTP profiles with static bottleneck attributes (capacity, latency, loss_rate, aqm_policy)
- Implement CTP operations: extract(), select(), transform(), merge(), replay()
- Compile CTPs to Linux tc (traffic control) commands
- Support CTP composition and algebra
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
4. CTP operations: extract, select, transform, merge, replay
5. Physical limit validation

---

## Execution Plane: Substrate Worker, NetGent, Telemetry

### 3. Substrate Worker (Port 8002) — D1 CRITICAL

**Location**: `./substrate-worker/`

**Purpose**: Data plane execution. Applies bottleneck regime conditions to the network using Linux kernel capabilities and collects packet traces and telemetry.

**Responsibilities**:
- Apply CTP configurations via tc qdisc management
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

**Dependencies**: Telemetry Service (for storing pcap files).

**Implementation**:
1. Flask server with privileged mode support (CAP_NET_ADMIN)
2. tc command executor for qdisc management
3. tshark/tcpdump integration for packet capture
4. iperf3 client for throughput measurement
5. ping-based RTT measurement
6. Pcap storage to mounted volume
7. Linux sysctl tuning

---

### 4. NetGent Service (Port 8003) — D2 HIGH

**Location**: `./netgent-service/`

**Purpose**: Application-level execution plane. Uses NFA (nondeterministic finite automaton) to specify and execute browser automation workflows, generating application-specific traffic and measuring QoE.

**Responsibilities**:
- Compile NetGent workflows from NFA specification
- Execute browser automation (YouTube, Netflix, Zoom, etc.)
- Collect QoE metrics: video startup time, rebuffer events, bitrate
- Coordinate network conditions with Substrate Worker
- Store workflow logs and artifacts

**Key Endpoints**:
- `POST /workflows/compile` — Compile NFA from spec
- `POST /workflows/execute` — Run workflow under current network conditions
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

**Dependencies**: Substrate Worker (network coordination), Telemetry Service (artifact storage).

**Implementation**:
1. NetGent NFA execution engine integration
2. NFA compiler from JSON specs
3. Selenium or Puppeteer for browser automation
4. QoE metric extractors per application
5. Workflow state logging and error handling
6. Timeout management (30-second default)
7. Artifact storage

---

### 5. Telemetry Service (Port 8004) — D3 HIGH

**Location**: `./telemetry-service/`

**Purpose**: Context plane data layer. Stores experiment results with contextual tree metadata spanning static bottleneck attributes, dynamic congestion pressure, application characteristics, and transport state.

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

## Service Interaction Flow

```
Orchestration Service (intent)
    ↓
Experiment API (experiment specification)
    ↓
CTP Service (validate bottleneck regime)
    ↓
Substrate Worker (configure bottleneck, start capture)
    ↓
NetGent Service (execute NFA workflow, collect QoE)
    ↓
Substrate Worker (stop capture, measure dynamic state)
    ↓
Telemetry Service (persist result + contextual tree)
    ↓
Experiment API (aggregate and return result)
```

Each service contributes to the final ExperimentResult:
- **CTP Service**: Validated bottleneck regime (static attributes)
- **Substrate Worker**: Pcap files, measured dynamic state, telemetry
- **NetGent Service**: QoE metrics, workflow artifacts
- **Telemetry Service**: Persistent storage, contextual tree tagging

---

## Core Requirements

The platform is designed to satisfy four key requirements:

1. **Controllability**: CTP operations (extract, select, transform, merge, replay) enable fine-grained network condition control
2. **Composability**: Services operate independently (weeks 1-2 with mocks) and compose (weeks 3-4 integration)
3. **Fidelity**: Substrate Worker verification ensures applied conditions match specifications within 5% tolerance
4. **Replicability**: Contextual trees capture all context; pcap traces enable offline replay

---

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

**Last Updated**: 2026-03-04 | **Status**: Design Phase | **Next**: Week 1-2 Parallel Implementation
