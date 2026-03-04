# Services Architecture

The Agentic Thin Waist consists of six microservices that form the critical infrastructure layer for network research data generation. Each service has a specific responsibility in the experiment pipeline.

## Service Overview

| Service | Port | Deliverable | Status | Dependencies |
|---------|------|-------------|--------|--------------|
| Experiment API | 8000 | D1 | Intent Plane | All services |
| CTP Service | 8001 | D1 | Representation Plane | None |
| Substrate Worker | 8002 | D1 | Execution Plane | Storage Service |
| NetGent Service | 8003 | D2 | Application Execution | Substrate Worker, Storage Service |
| Storage Service | 8004 | D3 | Data Persistence | None |
| Orchestration | 8005 | D5 | Agentic Orchestration | All services |

## Service Descriptions

### 1. Experiment API (Port 8000)

**Location**: `./experiment-api/`

**Purpose**: Central orchestration service that manages the experiment lifecycle from intent to results aggregation.

**Responsibilities**:
- Create and manage experiment records
- Coordinate between CTP, Substrate, NetGent, and Storage services
- Implement experiment state machine (pending → provisioning → running → complete → archived)
- Verify network configuration is applied before running workflows
- Aggregate results from multiple services

**Key Endpoints**:
- `POST /experiments` — Create new experiment
- `GET /experiments/{experiment_id}` — Get experiment status
- `GET /experiments` — List experiments with filtering
- `POST /experiments/{experiment_id}/execute` — Start execution
- `GET /experiments/{experiment_id}/results` — Fetch aggregated results

**Dataclass Contracts** (see shared/models/):
- `Experiment` — full specification with capacity, latency, application, duration
- `ExperimentResult` — results with pcap paths, bottleneck state, QoE metrics

**Dependencies**: All other services (see docker-compose.yml)

**Testing Criteria**:
- Experiment creation stores metadata correctly
- State transitions follow state machine rules
- Results aggregation merges outputs from Substrate + NetGent + Storage
- Bottleneck verification passes before workflow execution

**Implementation Guide**:
1. Implement Flask/FastAPI server with REST endpoints
2. Define experiment state machine: pending → provisioning → running → complete
3. Create HTTP clients for all dependent services
4. Implement result aggregation from Storage Service
5. Add request validation using Pydantic
6. Write integration tests verifying full experiment pipeline

**References**:
- NetUnicorn orchestration patterns: https://github.com/Aritro-BhumitraX/NetUnicorn
- Flask-RESTful documentation: https://flask-restful.readthedocs.io/

---

### 2. CTP Service (Port 8001)

**Location**: `./ctp-service/`

**Purpose**: Capacity-Throughput Profile (CTP) algebra service that translates high-level network conditions into Linux `tc` (traffic control) commands.

**Responsibilities**:
- Define CTP profiles: (capacity_mbps, latency_ms, loss_rate, aqm_policy)
- Translate CTPs to `tc` qdisc configurations
- Support CTP composition and algebra operations
- Verify network state matches configured CTP

**Key Endpoints**:
- `POST /ctps/validate` — Check if CTP is valid
- `POST /ctps/compile` — Compile CTP to tc commands
- `GET /ctps/presets` — List preset CTP profiles
- `POST /ctps/verify` — Verify network matches CTP

**Dataclass Contracts**:
```python
@dataclass
class NetReplicaConfig:
    capacity_mbps: float
    latency_ms: float
    buffer_size: Optional[int] = None
    aqm_policy: str = "fifo"  # or "codel", "pie", "fq_codel"
    ctp_profile: Optional[str] = None

@dataclass
class BottleneckState:
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    verification_passed: bool
```

**Dependencies**: None (independent service)

**Testing Criteria**:
- Valid CTPs produce valid tc commands
- CTP verification detects mismatches (>5% error acceptable)
- Preset profiles load and compile correctly
- AQM policies (fifo, codel, pie) translate to correct qdiscs

**Implementation Guide**:
1. Parse CTP profiles from JSON/dataclass definitions
2. Implement tc command generator for each AQM policy
3. Create network state measurement code (iperf3, ping for RTT)
4. Implement CTP algebra: composition, scaling, normalization
5. Add validation for physical limits (0 < capacity, 0 <= latency)

**References**:
- NetReplica controller.py: https://github.com/SNL-UCSB/netReplica/blob/main/controller.py
- Linux tc (traffic control) manual: https://man7.org/linux/man-pages/man8/tc.8.html
- AQM algorithms: https://tools.ietf.org/html/rfc7567 (AQM Recommendations)

---

### 3. Substrate Worker (Port 8002)

**Location**: `./substrate-worker/`

**Purpose**: Executes network conditions on the data plane using Linux kernel capabilities (tc, tshark for packet capture).

**Responsibilities**:
- Apply CTP configurations via `tc` qdisc management
- Collect network telemetry via `tshark` or tcpdump
- Measure bottleneck state (verify applied configuration)
- Execute privileged network operations
- Store raw pcap files and transport state snapshots

**Key Endpoints**:
- `POST /workers/configure` — Apply CTP to network interface
- `GET /workers/status` — Get current network configuration
- `POST /workers/capture/start` — Start packet capture (tshark)
- `POST /workers/capture/stop` — Stop capture, return pcap path
- `GET /workers/metrics` — Get measured throughput/RTT

**Dataclass Contracts**:
```python
@dataclass
class BottleneckState:
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    verification_passed: bool

@dataclass
class TelemetrySnapshot:
    timestamp: str
    interface: str
    tx_packets: int
    rx_packets: int
    tx_bytes: int
    rx_bytes: int
    tx_errors: int
    rx_errors: int
    packet_loss_percent: float
```

**Dependencies**: Storage Service (for storing pcap files)

**Testing Criteria**:
- Applied tc configuration matches requested CTP (within 5% tolerance)
- Packet captures produce valid pcap files
- RTT measurements accurate within 5% of configured latency
- Throughput measurements match configured capacity

**Implementation Guide**:
1. Set up Flask server with privileged mode support
2. Implement `tc` command executor (requires CAP_NET_ADMIN)
3. Integrate tshark or tcpdump for packet capture
4. Implement iperf3 client for throughput measurement
5. Create ping-based RTT measurement
6. Store pcap files to mounted volume (shared with Storage Service)
7. Add Linux sysctl tuning for reliability

**References**:
- Linux tc qdisc documentation: https://man7.org/linux/man-pages/man8/tc.8.html
- tshark documentation: https://www.wireshark.org/docs/man-pages/tshark.html
- tcpdump: https://www.tcpdump.org/
- NetReplica implementation: https://github.com/SNL-UCSB/netReplica

---

### 4. NetGent Service (Port 8003)

**Location**: `./netgent-service/`

**Purpose**: Executes application-level workflows (NFA-based browser automation) to generate application-specific traffic patterns and measure quality-of-experience (QoE) metrics.

**Responsibilities**:
- Compile NetGent workflows (NFAs) from specification
- Execute browser automation workflows (YouTube, Netflix, Zoom, etc.)
- Collect QoE metrics (video startup time, rebuffer events, bitrate)
- Coordinate with Substrate Worker for network state
- Store workflow execution results and artifacts

**Key Endpoints**:
- `POST /workflows/compile` — Compile NFA from spec
- `POST /workflows/execute` — Run workflow under network conditions
- `GET /workflows/results/{workflow_id}` — Get workflow execution results
- `GET /workflows/available` — List available workflows
- `POST /workflows/qoe/measure` — Extract QoE metrics from logs

**Dataclass Contracts**:
```python
@dataclass
class WorkflowResult:
    workflow_id: str
    application: str  # "youtube", "netflix", "zoom"
    status: str  # "success", "failure", "timeout"
    states_executed: List[str]
    artifacts_collected: dict
    duration_seconds: float
    qoe_metrics: dict  # startup_time_ms, rebuffer_events, bitrate
    error: Optional[str] = None

@dataclass
class QoEMetrics:
    video_startup_time_ms: float
    mean_bitrate_mbps: float
    bitrate_changes: int
    rebuffer_events: int
    rebuffer_duration_ms: float
    stall_duration_ms: float
```

**Dependencies**: Substrate Worker (to control network conditions), Storage Service (to store artifacts)

**Testing Criteria**:
- Workflows compile without errors
- YouTube workflow generates consistent QoE metrics
- Zoom audio/video quality metrics are measurable
- Workflow results correctly tag with application and CTP context
- Timeout handling works correctly (30-second default)

**Implementation Guide**:
1. Integrate existing NetGent NFA execution engine
2. Implement workflow compiler from JSON specs to executable states
3. Set up browser automation using Selenium or Puppeteer
4. Create QoE metric extractors for each application
5. Implement workflow state logging and error handling
6. Add timeout management and graceful shutdown
7. Store workflow logs and artifacts to Storage Service

**References**:
- NetGent NFA-based workflows: Private SNL-UCSB repo
- Selenium WebDriver: https://www.selenium.dev/
- Puppeteer (Node.js browser automation): https://pptr.dev/
- QoE measurement standards: https://en.wikipedia.org/wiki/Quality_of_experience

---

### 5. Storage Service (Port 8004)

**Location**: `./storage-service/`

**Purpose**: Centralized storage for experiment results, telemetry, and artifacts with powerful query interface and contextual tagging.

**Responsibilities**:
- Store experiment results with contextual tree metadata
- Provide query API for filtering by experiment, application, CTP, date range
- Archive pcap files and workflow artifacts
- Tag results with context (c_static, c_dyn, c_app, c_trans)
- Enable data analysis and visualization

**Key Endpoints**:
- `POST /results` — Store experiment result
- `GET /results` — Query results with filters
- `GET /results/{result_id}` — Get single result
- `POST /artifacts/{artifact_id}/upload` — Store pcap or artifact file
- `GET /artifacts/{artifact_id}` — Retrieve artifact
- `POST /tags` — Tag results with custom metadata

**Dataclass Contracts**:
```python
@dataclass
class ContextualTreeNode:
    c_static: dict  # capacity_mbps, latency_ms, buffer_size, aqm
    c_dyn: dict     # ctp_cluster_id, measured_state
    c_app: dict     # application_name, workflow_spec
    c_trans: dict   # protocol, congestion_control

@dataclass
class ExperimentResult:
    experiment_id: str
    result_id: str
    status: str  # "success", "failure", "timeout"
    pcap_paths: List[str]
    bottleneck_state: BottleneckState
    qoe_metrics: dict
    transport_state: dict
    duration_seconds: float
    timestamp: str
    contextual_tree: ContextualTreeNode

@dataclass
class QueryFilter:
    experiment_id: Optional[str] = None
    application: Optional[str] = None
    capacity_mbps_range: Optional[Tuple[float, float]] = None
    latency_ms_range: Optional[Tuple[float, float]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    tags: Optional[List[str]] = None
```

**Dependencies**: None (independent data layer)

**Testing Criteria**:
- Results stored with complete contextual tree
- Query filters return correct result subsets
- Artifacts stored and retrievable
- Tag operations work correctly
- Database schema supports all data types

**Implementation Guide**:
1. Set up database (SQLite for dev, PostgreSQL for production)
2. Define SQLAlchemy ORM models for results, artifacts, tags
3. Implement REST endpoints for CRUD operations
4. Create query builder supporting filters and date ranges
5. Add file upload/download for pcap and artifacts
6. Implement contextual tree storage and tagging
7. Add index optimization for common queries
8. Write migration scripts for schema evolution

**References**:
- SQLAlchemy ORM: https://www.sqlalchemy.org/
- PostgreSQL: https://www.postgresql.org/
- Flask-RESTful: https://flask-restful.readthedocs.io/

---

### 6. Orchestration Service (Port 8005)

**Location**: `./orchestration/`

**Purpose**: Agentic orchestration using Claude + OpenClaw to interpret natural language research intents and generate experiment specifications.

**Responsibilities**:
- Accept natural language research intents
- Use Claude to reason about network conditions and applications
- Declare tools and skills for all services (via OpenClaw)
- Generate experiment JSON specifications
- Dispatch experiments to Experiment API
- Handle multi-step reasoning for complex intents

**Key Endpoints**:
- `POST /intent` — Submit research intent in natural language
- `GET /status/{request_id}` — Check orchestration status
- `GET /tools` — List available tools (for OpenClaw)
- `GET /skills` — List available skills (for OpenClaw)

**Configuration Files**:
- `TOOLS.md` — OpenClaw tool declarations (Experiment API, CTP Service, Storage Service endpoints)
- `SKILLS.md` — OpenClaw skill definitions (multi-step workflows like "compare applications")
- `prompts/system.md` — System prompt for Claude
- `prompts/examples.md` — Few-shot examples for intent → experiment mapping

**Example Dataclass Contracts**:
```python
@dataclass
class ResearchIntent:
    intent_text: str
    context: Optional[dict] = None  # e.g., {"default_duration": 30}
    preferences: Optional[dict] = None  # e.g., {"num_trials": 3}

@dataclass
class GeneratedExperiment:
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float
    application: str
    duration_seconds: int
    num_trials: int
    reasoning: str  # Claude's explanation
```

**Dependencies**: All services (via HTTP)

**Testing Criteria**:
- Intent "Compare YouTube vs Zoom at 10, 25, 50 Mbps" generates valid experiments
- Generated experiments have reasonable defaults
- Claude reasoning is captured and logged
- Multi-step intents (e.g., "Test three apps across bandwidth range") create multiple experiments
- Error handling for malformed intents is graceful

**Implementation Guide**:
1. Set up Claude API integration (via Anthropic SDK or REST)
2. Implement OpenClaw tool/skill declaration system
3. Create prompt templates for intent → experiment mapping
4. Implement HTTP client for all backend services
5. Add request/response logging for debugging
6. Write few-shot examples for Claude in prompts/
7. Implement error recovery and clarification requests
8. Add validation that generated experiments are within reasonable bounds

**References**:
- OpenClaw framework: [Internal SNL-UCSB documentation]
- Claude API: https://docs.anthropic.com/claude/reference/
- Prompt engineering best practices: https://docs.anthropic.com/claude/docs/prompt-engineering

---

## Service Interaction Patterns

### Experiment Execution Flow

```
1. Experiment API (POST /experiments)
   ↓
2. CTP Service (validates capacity/latency)
   ↓
3. Substrate Worker (applies tc, starts tshark)
   ↓
4. NetGent Service (executes application workflow)
   ↓
5. Substrate Worker (collects pcap, measures throughput/RTT)
   ↓
6. Storage Service (stores results with contextual tree)
   ↓
7. Experiment API (aggregates and returns final result)
```

### Result Aggregation

Each service contributes to the final result:
- **CTP Service**: Network configuration validated
- **Substrate Worker**: Bottleneck state, pcap paths, telemetry
- **NetGent Service**: QoE metrics, workflow artifacts
- **Storage Service**: Persistent storage, contextual tagging

### Error Handling

- If CTP validation fails → return 400 Bad Request
- If Substrate Worker fails to apply tc → return 500, retry with exponential backoff
- If NetGent workflow times out → return 408, preserve partial artifacts
- If Storage Service is down → queue results in memory, retry on recovery

## Development Guidelines

1. **Keep services independent**: Each service should function with mocked dependencies
2. **Use dataclasses for contracts**: All service-to-service communication uses defined dataclasses
3. **Version APIs**: Use semantic versioning (v1, v2) for API endpoints
4. **Log extensively**: All services log to stdout for Docker container logging
5. **Health checks**: All services implement `/health` endpoints
6. **Testing**: Write unit tests for core logic, integration tests for service interactions

---

**Last Updated**: 2026-03-04
**Status**: Architecture Phase
**Next Milestone**: D1 Service Implementation (Week 1-2)
