# Shared Model Definitions

This directory contains dataclass definitions for all service-to-service communication contracts. These are the single source of truth for data structures spanning the Intent, Representation, and Execution planes.

## Core Dataclasses

### Experiment

```python
@dataclass
class Experiment:
    """Full experiment specification with Intent, Representation, and application context.

    Intent Plane: Specifies the bottleneck regime via static attributes and dynamic CTP.
    Representation Plane: Names and configures Cross-Traffic Profiles.
    Execution Plane: Application and capture configuration.
    """
    experiment_id: str                              # Unique identifier

    # Intent Plane: Static Bottleneck Attributes
    download_mbps: float                            # Link capacity (downlink)
    upload_mbps: float                              # Link capacity (uplink)
    latency_ms: float                               # RTT latency in milliseconds
    qdisc: str = "fifo"                            # Queue discipline (AQM policy)
    buffer_size: Optional[int] = None              # Queue depth in bytes

    # Representation Plane: CTP (Cross-Traffic Profile)
    ctp_name: Optional[str] = None                 # CTP identifier
    ctp_path: Optional[str] = None                 # Path to CTP artifact
    ctp_operations: List[str] = field(default_factory=list)  # CTP ops: extract, select, transform, merge, replay

    # Application Context
    application: str = ""                          # "youtube", "netflix", "zoom", etc.
    duration_seconds: int = 60                     # Experiment duration
    num_trials: int = 1                            # Number of repetitions

    # Capture and Success Metrics
    capture: Optional[dict] = None                 # Capture config (interface, filter, etc.)
    success_metrics: List['SuccessMetric'] = field(default_factory=list)  # Threshold-based success criteria

    # Metadata and Lifecycle
    metadata: dict = field(default_factory=dict)   # Custom metadata
    status: str = "pending"                         # pending, provisioning, running, complete, failed
    created_at: Optional[str] = None                # ISO 8601 timestamp
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
```

**Usage**:
- Created by Orchestration Service or user intent
- Used by Experiment API to track state and orchestrate workflow
- Stored by Storage Service for audit and analysis

---

### SuccessMetric

```python
@dataclass
class SuccessMetric:
    """Threshold-based success criterion for experiment completion."""
    name: str                           # Metric name (e.g., "startup_time_ms")
    source: str                         # Source: "qoe", "transport", "bottleneck"
    threshold: float                    # Target threshold value
    direction: str                      # "min" (lower is better) or "max" (higher is better)
    description: Optional[str] = None   # Human-readable explanation
```

**Usage**:
- Defined in Experiment during Intent specification
- Evaluated by Experiment API after ExperimentResult collection
- Used to determine overall experiment success or failure

---

### AnalysisResult

```python
@dataclass
class AnalysisResult:
    """Post-experiment analysis computed from trial results."""
    metrics_computed: dict              # {metric_name: computed_value}
    thresholds_met: dict                # {metric_name: bool (threshold satisfied)}
    anomalies: List[dict] = field(default_factory=list)  # [{type, severity, description}]
    raw_data_paths: List[str] = field(default_factory=list)  # Paths to pcaps, logs, HAR
    summary: Optional[str] = None       # Human-readable analysis summary
```

**Usage**:
- Created by Experiment API after analyzing all trials
- Stored with ExperimentResult for audit
- Guides iteration and experiment refinement

---

### ExperimentResult

```python
@dataclass
class ExperimentResult:
    """Complete result from one trial of an experiment."""
    experiment_id: str                  # Reference to Experiment
    trial_number: int                   # Which trial (1, 2, 3, ...)
    status: str                         # "success", "failure", "timeout"

    # Execution Plane: Applied Bottleneck Verification
    shaping_applied: BottleneckState    # Verification of actual network conditions

    # Captured Data
    captures: List[dict] = field(default_factory=list)  # [{capture_id, path, filter, packets}]
    duration_actual: float = 0.0        # Actual trial duration

    # Analysis Results
    metrics: dict = field(default_factory=dict)         # Application-level + network-level metrics
    analysis: Optional[AnalysisResult] = None           # Post-hoc analysis

    # Errors and Metadata
    errors: List[str] = field(default_factory=list)     # Collected errors or warnings
    created_at: Optional[str] = None                     # ISO 8601 timestamp
```

**Usage**:
- Created by Substrate Worker (Execution) and NetGent Service (Application)
- Aggregated by Experiment API
- Stored by Storage Service with full audit trail

---

### BottleneckState

```python
@dataclass
class BottleneckState:
    """Verification of bottleneck regime: static attributes + measured dynamic pressure.

    The bottleneck regime is defined by:
    - Static attributes: capacity, base latency, buffering (buffer_size), queue management (qdisc)
    - Dynamic pressure: Cross-Traffic Profile temporal structure (measured via CTP operations)
    """
    # Static Bottleneck Attributes
    download_mbps: float                # Configured download capacity
    upload_mbps: float                  # Configured upload capacity
    latency_ms: float                   # Configured RTT latency
    qdisc: str = "fifo"                 # Configured queue discipline
    buffer_size: Optional[int] = None   # Configured queue depth

    # Measured Conditions
    measured_download_mbps: Optional[float] = None  # Measured throughput (downlink)
    measured_upload_mbps: Optional[float] = None    # Measured throughput (uplink)
    measured_rtt_ms: Optional[float] = None         # Measured round-trip time
    packet_loss_percent: float = 0.0
    jitter_ms: float = 0.0

    # Verification Status
    verified: bool = False              # True if measured matches configured within tolerance
```

**Verification Rules**:
- `abs(measured_download - configured_download) / configured_download < 0.05` (5% tolerance)
- `abs(measured_rtt - configured_latency) / configured_latency < 0.05` (5% tolerance)

**Usage**:
- Created by Substrate Worker during Execution Plane
- Checked by Experiment API before proceeding with application workflows
- Stored with ExperimentResult for audit trail

---

### ContextualTreeNode

```python
@dataclass
class ContextualTreeNode:
    """Rich metadata tagging results with full cross-plane context.

    Enables dimensional queries across Intent, Representation, and Execution dimensions.
    """

    c_static: dict  # Static bottleneck attributes (Intent Plane)
        # download_mbps: float
        # upload_mbps: float
        # latency_ms: float
        # buffer_size: Optional[int]
        # qdisc: str (AQM policy)

    c_dyn: dict     # Dynamic pressure via CTP (Representation Plane)
        # ctp_name: str
        # ctp_operations: List[str]  # extract, select, transform, merge, replay
        # measured_throughput: float
        # measured_rtt: float
        # packet_loss_percent: float

    c_app: dict     # Application context (Execution Plane)
        # application: str
        # workflow_spec: str
        # duration_seconds: int
        # qoe_metrics: dict

    c_trans: dict   # Transport/protocol context (Execution Plane)
        # protocol: str (tcp, udp, etc.)
        # congestion_control: str (cubic, bbr, etc.)
        # source_port: int
        # destination_port: int
```

**Purpose**: Enable rich cross-plane queries like:
- "Show me YouTube performance under all CUBIC flows with FIFO qdisc"
- "Compare CoDel vs FIFO for the same static capacity with identical CTP"
- "Identify outliers in startup time across all CTP variations"

**Usage**:
- Constructed by Experiment API from Experiment, ExperimentResult, and BottleneckState components
- Stored by Storage Service as nested JSON
- Queried by researchers and analysis tools

---

### NetReplicaConfig

```python
@dataclass
class NetReplicaConfig:
    """Network replica configuration for Substrate Worker deployment.

    Specifies the complete Execution Plane setup including static bottleneck
    attributes and capture infrastructure.
    """
    # Static Bottleneck Attributes
    download_mbps: float                    # Link capacity (downlink)
    upload_mbps: float                      # Link capacity (uplink)
    latency_ms: float                       # RTT latency
    qdisc: str = "fifo"                     # Queue discipline (AQM)
    buffer_size: Optional[int] = None       # Queue depth (bytes)
    loss_rate: float = 0.0                  # Packet loss [0, 1]
    jitter_ms: float = 0.0                  # RTT variance

    # Capture Infrastructure
    capture_dir: str = "/tmp/captures"      # Directory for packet captures
    upstream_iface: str = "eth0"            # Upstream network interface
    downstream_iface: str = "eth1"          # Downstream network interface
    delay_iface: Optional[str] = None       # Latency injection interface

    # Namespace and CTP
    namespace: Optional[str] = None         # Network namespace (if isolated)
    ctp_dir: Optional[str] = None           # Directory containing CTP artifacts
```

**Validation**:
- `0 < download_mbps <= 10000`
- `0 < upload_mbps <= 10000`
- `0 <= latency_ms <= 10000`
- `0 <= loss_rate <= 1.0`
- `qdisc in ["fifo", "codel", "pie", "fq_codel", "sfq"]`

**Usage**:
- Created by Experiment API or Orchestration Service
- Validated by CTP Service (Representation Plane)
- Applied by Substrate Worker (Execution Plane)

---

### WorkflowResult

```python
@dataclass
class WorkflowResult:
    """Application workflow execution result from NFA execution.

    Represents the complete lifecycle and outcomes of running an application
    workflow under the specified bottleneck regime.
    """
    workflow_id: str                    # Reference to NFA workflow spec
    experiment_id: str                  # Reference to parent experiment
    application: str                    # "youtube", "zoom", etc.
    status: str                         # "success", "failure", "timeout"
    start_time: str                     # ISO 8601
    end_time: Optional[str]             # ISO 8601
    duration_seconds: float             # Actual execution time
    states_executed: List[str]          # NFA states completed
    artifacts_collected: dict           # {"har": path, "screenshots": [...], "logs": [...]}
    qoe_metrics: Optional[dict] = None  # Extracted QoE metrics if success
    error: Optional[str] = None         # Error message if failed
    nfa: Optional[dict] = None          # NFA specification used
```

**Usage**:
- Created by NetGent Service (Application execution)
- Artifacts stored by Storage Service
- QoE metrics included in ExperimentResult metrics

---

### QoEMetrics

```python
@dataclass
class QoEMetrics:
    """Video quality-of-experience metrics."""
    video_startup_time_ms: float        # Time from play click to first frame
    mean_bitrate_mbps: float            # Average video bitrate
    bitrate_changes: int                # Number of bitrate switches
    rebuffer_events: int                # Number of stall events
    rebuffer_duration_ms: float         # Total stall time
    stall_duration_ms: float = 0.0      # Synonym for rebuffer_duration
    mean_watched_bitrate_mbps: Optional[float] = None
    max_bitrate_mbps: Optional[float] = None
    min_bitrate_mbps: Optional[float] = None
    video_resolution_p: Optional[int] = None  # 480, 720, 1080, etc.
    frame_rate_fps: Optional[float] = None
```

**Per-Application Variations**:

**YouTube**:
- All standard QoE metrics
- resolution_p, frame_rate_fps

**Netflix**:
- Startup time, bitrate, rebuffers
- profile (SD, HD, 4K)

**Zoom**:
- video_quality_subjective (scales 1-5)
- audio_quality (presence of artifacts)
- packet_loss_percent
- No traditional "bitrate" but frame rate

**Usage**:
- Extracted by NetGent Service (D2) from HAR, browser DevTools
- Stored with WorkflowResult
- Queried by researchers for QoE analysis

---

## Module Organization

```
shared/models/
├── __init__.py                  # Exports all dataclasses
├── experiment.py                # Experiment, ExperimentResult, SuccessMetric, AnalysisResult
├── network.py                   # BottleneckState, NetReplicaConfig
├── ctp.py                       # CTP-specific types and operations
├── workflow.py                  # WorkflowResult, QoEMetrics
└── README.md                    # This file (complete reference)
```

### Import Pattern

```python
# In any service:
from shared.models import (
    Experiment,
    ExperimentResult,
    SuccessMetric,
    AnalysisResult,
    BottleneckState,
    ContextualTreeNode,
    NetReplicaConfig,
    WorkflowResult,
    QoEMetrics
)
```

## JSON Serialization

All dataclasses support JSON serialization for HTTP communication:

```python
from dataclasses import asdict
import json

# Serialize to JSON
result = ExperimentResult(...)
json_str = json.dumps(asdict(result), default=str)

# Deserialize from JSON
data = json.loads(json_str)
result = ExperimentResult(**data)
```

For better control, use Pydantic models in validation:

```python
from pydantic import BaseModel, validator

class ExperimentModel(BaseModel):
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    # ... fields ...

    @validator('capacity_mbps')
    def capacity_positive(cls, v):
        if v <= 0:
            raise ValueError('capacity must be positive')
        return v
```

## Versioning Strategy

If you need to change a dataclass:

1. **Add a new version** (e.g., `ExperimentV2`)
2. **Create a migration function**:
   ```python
   def migrate_experiment_v1_to_v2(v1: Experiment) -> ExperimentV2:
       return ExperimentV2(
           experiment_id=v1.experiment_id,
           # ... map v1 fields to v2 ...
       )
   ```
3. **Support both versions** in services temporarily
4. **Deprecate after migration period**

## Testing Dataclasses

```python
# tests/test_models.py
from shared.models import (
    Experiment, SuccessMetric, BottleneckState, ExperimentResult
)

def test_experiment_with_intent_and_representation():
    """Test Experiment with Intent (static attrs) and Representation (CTP) planes."""
    success = SuccessMetric(
        name="startup_time_ms",
        source="qoe",
        threshold=2000,
        direction="min",
        description="Video startup under 2 seconds"
    )

    exp = Experiment(
        experiment_id="test-001",
        download_mbps=10,
        upload_mbps=5,
        latency_ms=50,
        qdisc="codel",
        application="youtube",
        duration_seconds=60,
        ctp_name="web-browsing-2024",
        ctp_operations=["extract", "select", "replay"],
        success_metrics=[success]
    )
    assert exp.status == "pending"
    assert exp.num_trials == 1

def test_bottleneck_state_verification():
    """Test BottleneckState with static/dynamic verification."""
    state = BottleneckState(
        download_mbps=10.0,
        upload_mbps=5.0,
        latency_ms=50,
        qdisc="fifo",
        measured_download_mbps=9.8,
        measured_upload_mbps=4.9,
        measured_rtt_ms=52,
        verified=True
    )
    assert state.verified == True
```

## Terminology Reference

**CTP = Cross-Traffic Profile** (NOT "Capacity-Throughput Profile")
- Represents temporal structure of aggregate demand
- Part of Representation Plane
- Operations: extract(), select(), transform(), merge(), replay()

**Bottleneck Regime** = Static attributes + Dynamic pressure
- Static: capacity, latency, buffering, queue management (AQM)
- Dynamic: Cross-Traffic Profile temporal patterns

**Three Planes**:
- **Intent**: Link(), Bottleneck() abstractions
- **Representation**: CrossTraffic(), CTPs as reusable artifacts
- **Execution**: tc (traffic control), tshark (capture), tcpreplay (replay)

**netUnicorn SOA**:
- client (user interface)
- core/mediation (orchestration)
- deployment (compiler, connectivity manager)
- execution (processor, gateway)
- datastore (results and artifacts)

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
**Team**: Prof. Arpit Gupta (PI), Jaber, Eugene, Haarika, Manni, Sylee
