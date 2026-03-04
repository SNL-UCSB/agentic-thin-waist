# Shared Model Definitions

This directory contains dataclass definitions for all service-to-service communication contracts. These are the single source of truth for data structures.

## Core Dataclasses

### Experiment

```python
@dataclass
class Experiment:
    """Full experiment specification for network research."""
    experiment_id: str          # Unique identifier
    capacity_mbps: float        # Link capacity in Mbps
    latency_ms: float           # RTT latency in milliseconds
    loss_rate: float = 0.0      # Packet loss rate [0, 1]
    aqm_policy: str = "fifo"    # Active queue management policy
    application: str            # "youtube", "netflix", "zoom", etc.
    duration_seconds: int       # Experiment duration
    num_trials: int = 1         # Number of repetitions
    metadata: dict = field(default_factory=dict)  # Custom metadata
    status: str = "pending"     # pending, provisioning, running, complete, failed
    created_at: Optional[str] = None  # ISO 8601 timestamp
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
```

**Usage**:
- Created by Orchestration Service (D5)
- Used by Experiment API (D1) to track state
- Stored by Storage Service (D3) for audit

---

### ExperimentResult

```python
@dataclass
class ExperimentResult:
    """Complete result from one trial of an experiment."""
    experiment_id: str                  # Reference to Experiment
    trial_number: int                   # Which trial (1, 2, 3, ...)
    status: str                         # "success", "failure", "timeout"
    bottleneck_state: BottleneckState   # Verification of applied network
    pcap_path: str                      # Path to captured pcap file
    qoe_metrics: dict                   # Application-level metrics
    transport_state: dict               # Network-level statistics
    contextual_tree: ContextualTreeNode # Rich metadata tagging
    error: Optional[str] = None         # Error message if failed
    created_at: Optional[str] = None    # ISO 8601 timestamp
```

**Usage**:
- Created by Substrate Worker (D1) + NetGent Service (D2)
- Aggregated by Experiment API (D1)
- Stored by Storage Service (D3)

---

### BottleneckState

```python
@dataclass
class BottleneckState:
    """Verification that network conditions match specification."""
    configured_capacity: float      # Requested capacity (Mbps)
    configured_latency: float       # Requested latency (ms)
    measured_throughput: float      # Measured throughput (Mbps)
    measured_rtt: float             # Measured round-trip time (ms)
    verification_passed: bool = True
    packet_loss_percent: float = 0.0
    jitter_ms: float = 0.0
```

**Verification Rules**:
- `abs(measured_throughput - configured_capacity) / configured_capacity < 0.05` (5% tolerance)
- `abs(measured_rtt - configured_latency) / configured_latency < 0.05` (5% tolerance)

**Usage**:
- Created by Substrate Worker (D1)
- Checked by Experiment API (D1) before proceeding with workflows
- Stored with results for audit trail

---

### ContextualTreeNode

```python
@dataclass
class ContextualTreeNode:
    """Rich metadata tagging results with full context."""

    c_static: dict  # Static configuration
        # capacity_mbps: float
        # latency_ms: float
        # buffer_size: Optional[int]
        # aqm_policy: str

    c_dyn: dict     # Dynamic network state
        # ctp_cluster_id: str
        # measured_throughput: float
        # measured_rtt: float
        # packet_loss_percent: float

    c_app: dict     # Application context
        # application: str
        # workflow_spec: str
        # duration_seconds: int

    c_trans: dict   # Transport/protocol context
        # protocol: str (tcp, udp, etc.)
        # congestion_control: str (cubic, bbr, etc.)
        # source_port: int
        # destination_port: int
```

**Purpose**: Enable rich queries like:
- "Show me YouTube performance under all CUBIC flows"
- "Compare FIFO vs CoDel for the same capacity"
- "Identify outliers in startup time across all conditions"

**Usage**:
- Constructed by Experiment API (D1) from result components
- Stored by Storage Service (D3) as nested JSON
- Queried by researchers for analysis

---

### NetReplicaConfig (CTP)

```python
@dataclass
class NetReplicaConfig:
    """Capacity-Throughput Profile: complete network specification."""
    capacity_mbps: float                    # Link capacity
    latency_ms: float                       # RTT latency
    loss_rate: float = 0.0                  # Packet loss [0, 1]
    aqm_policy: str = "fifo"                # AQM algorithm
    buffer_size: Optional[int] = None       # Queue depth (bytes)
    jitter_ms: float = 0.0                  # RTT variance
    ctp_profile: Optional[str] = None       # Preset name if applicable
```

**Validation**:
- `0 < capacity_mbps <= 10000`
- `0 <= latency_ms <= 10000`
- `0 <= loss_rate <= 1.0`
- `aqm_policy in ["fifo", "codel", "pie", "fq_codel", "sfq"]`

**Usage**:
- Created by Orchestration Service or Experiment API
- Validated by CTP Service (D1)
- Applied by Substrate Worker (D1)

---

### WorkflowResult

```python
@dataclass
class WorkflowResult:
    """Application workflow execution result."""
    workflow_id: str                    # Reference to workflow spec
    experiment_id: str                  # Reference to experiment
    application: str                    # "youtube", "zoom", etc.
    status: str                         # "success", "failure", "timeout"
    start_time: str                     # ISO 8601
    end_time: Optional[str]             # ISO 8601
    duration_seconds: float
    states_executed: List[str]          # NFA states completed
    artifacts_collected: dict           # {"har": path, "screenshots": [...]}
    qoe_metrics: Optional[dict] = None  # QoE metrics if success
    error: Optional[str] = None         # Error message if failed
```

**Usage**:
- Created by NetGent Service (D2)
- Artifacts stored by Storage Service (D3)
- QoE metrics included in ExperimentResult

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
├── __init__.py          # Exports all dataclasses
├── experiment.py        # Experiment, ExperimentResult, ContextualTreeNode
├── network.py           # BottleneckState, NetReplicaConfig
├── ctp.py               # CTP-specific types
├── workflow.py          # WorkflowResult, QoEMetrics
└── README.md            # This file
```

### Import Pattern

```python
# In any service:
from shared.models import (
    Experiment,
    ExperimentResult,
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
from shared.models import Experiment, BottleneckState

def test_experiment_creation():
    exp = Experiment(
        experiment_id="test-001",
        capacity_mbps=10,
        latency_ms=50,
        application="youtube",
        duration_seconds=60
    )
    assert exp.status == "pending"
    assert exp.num_trials == 1

def test_bottleneck_state():
    state = BottleneckState(
        configured_capacity=10.0,
        configured_latency=50,
        measured_throughput=9.8,
        measured_rtt=52
    )
    assert state.verification_passed == True
```

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
