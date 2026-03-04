# Experiment API Service

**Port**: 8000
**Deliverable**: D1 (Network Virtualization Substrate - Intent Plane)
**Lead**: Jaber
**PI**: Prof. Arpit Gupta
**Priority**: CRITICAL
**Status**: Implementation Ready

## Purpose

The Experiment API is the **Intent Plane** of the Bottleneck Service. It provides the high-level, user-facing interface for specifying and executing network bottleneck experiments. The Intent Plane abstracts the complexity of applying static bottleneck attributes (capacity, base latency, buffering, queue management) and dynamic congestion pressure (specified via Cross-Traffic Profiles) into a simple, composable experiment specification.

The Experiment API is responsible for:

1. **Intent specification**: Accept experiment definitions with static bottleneck regime attributes and dynamic CTP parameters
2. **Experiment orchestration**: Coordinate Intent Plane (Link, Bottleneck), Representation Plane (CrossTraffic with CTP operations), and Execution Plane (tc, tshark, tcpreplay)
3. **Bottleneck regime management**: Manage the combination of static attributes and dynamic pressure that defines a bottleneck regime
4. **Lifecycle management**: Create, validate, provision, execute, and archive experiments with state machine enforcement
5. **Result aggregation**: Collect measurements and analysis from multiple services into unified ExperimentResult
6. **Quality attributes**: Enforce controllability, composability, fidelity, and replicability throughout the experiment lifecycle

## Architecture: NetForge Three-Plane Model

The Experiment API maps the Intent Plane to NetForge's three-layer abstraction:

```
┌─────────────────────────────────────────────────────────────┐
│            INTENT PLANE (Experiment API :8000)              │
│  - User specifies bottleneck regime (static + dynamic)      │
│  - Link(), Bottleneck() dataclass definition                │
│  - CTP selection and validation                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      REPRESENTATION PLANE (CTP Service :8001)               │
│  - CrossTraffic() with CTP operations                       │
│  - CTP operations: extract(), select(), transform(),        │
│    merge(), replay()                                        │
│  - Maps intent to network conditions                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       EXECUTION PLANE (Substrate Worker :8002)              │
│  - tc (traffic control) for bottleneck enforcement          │
│  - tshark for packet capture                                │
│  - tcpreplay for traffic generation                         │
└─────────────────────────────────────────────────────────────┘
```

### Service Dependencies

```
┌──────────────────────┐
│ Orchestration/Client │
└──────────┬───────────┘
           │ POST /experiments
           ▼
┌──────────────────────────────────┐
│ EXPERIMENT API (Intent Plane)    │
│ ┌────────────────────────────┐   │
│ │ Experiment State Machine   │   │
│ │ Bottleneck Regime Manager  │   │
│ └────────────────────────────┘   │
└─┬─────────────┬──────────────┬───┘
  │             │              │
  ▼             ▼              ▼
CTP Service  Substrate     NetGent Service
:8001        Worker:8002   :8003
  │             │              │
  └─────────────┼──────────────┘
                │
                ▼
         Storage Service
             :8004
```

## Core Concepts

### Bottleneck Regime

A **bottleneck regime** is defined by:
- **Static attributes** (Intent Plane): capacity (Mbps), base latency (ms), buffer size (bytes), queue discipline (AQM policy)
- **Dynamic congestion pressure** (Representation Plane): specified via a Cross-Traffic Profile (CTP) name and operations

The Experiment API synthesizes these into a coherent bottleneck specification that maps to Substrate Worker's execution model.

### Cross-Traffic Profile (CTP)

A **CTP** captures realistic cross-traffic patterns for reproducible network experimentation. It encodes:
- Network measurement data (PCAP, flow traces, aggregate statistics)
- Operations to transform it: `extract()` (isolate specific flows), `select()` (choose subset), `transform()` (modify intensity), `merge()` (combine profiles), `replay()` (schedule on network)

The Experiment API references CTPs by name; the CTP Service handles validation and transformation.

## API Specification

### 1. Create Experiment

**Endpoint**: `POST /experiments`

**Request**:
```json
{
  "experiment_id": "youtube-10mbps-ctp-001",
  "capacity_mbps": 10.0,
  "latency_ms": 50,
  "buffer_size": 262144,
  "aqm_policy": "fq_codel",
  "ctp_name": "caffeine-mix-2024",
  "ctp_operations": ["extract:dns", "transform:scale=0.5"],
  "application": "youtube",
  "workflow_spec": "watch-video-60s",
  "duration_seconds": 60,
  "num_trials": 3,
  "capture_pcap": true,
  "metadata": {
    "researcher": "jaber@example.com",
    "study": "qoe-under-congestion",
    "hypothesis": "fq_codel improves bitrate stability"
  }
}
```

**Response** (201 Created):
```json
{
  "experiment_id": "youtube-10mbps-ctp-001",
  "status": "pending",
  "created_at": "2026-03-04T10:00:00Z",
  "bottleneck_regime": {
    "static": {
      "capacity_mbps": 10.0,
      "latency_ms": 50,
      "buffer_size": 262144,
      "aqm_policy": "fq_codel"
    },
    "dynamic": {
      "ctp_name": "caffeine-mix-2024",
      "ctp_operations": ["extract:dns", "transform:scale=0.5"],
      "ctp_validated": false
    }
  },
  "estimated_duration_seconds": 180,
  "_links": {
    "self": "/experiments/youtube-10mbps-ctp-001",
    "execute": "/experiments/youtube-10mbps-ctp-001/execute",
    "results": "/experiments/youtube-10mbps-ctp-001/results"
  }
}
```

**Validation**:
- capacity_mbps > 0 (Substrate capacity constraint)
- latency_ms >= 0 (base RTT)
- buffer_size > 0 (queue buffer in bytes)
- aqm_policy in ["fifo", "codel", "pie", "fq_codel", "cake"] (kernel tc modules)
- ctp_name exists and is registered (CTP Service validation)
- ctp_operations are valid: extract, select, transform, merge, replay
- application in list of supported apps
- workflow_spec matches application capabilities
- duration_seconds > 0
- num_trials >= 1
- experiment_id is unique

**Error Codes**:
- 400 Bad Request — validation failed (static attributes or workflow)
- 404 Not Found — ctp_name not found in CTP Service
- 409 Conflict — experiment_id already exists
- 503 Service Unavailable — backend service (CTP, Substrate) unreachable

---

### 2. Get Experiment Status

**Endpoint**: `GET /experiments/{experiment_id}`

**Response** (200 OK):
```json
{
  "experiment_id": "youtube-10mbps-ctp-001",
  "status": "running",
  "created_at": "2026-03-04T10:00:00Z",
  "started_at": "2026-03-04T10:00:10Z",
  "bottleneck_regime": {
    "static": {
      "capacity_mbps": 10.0,
      "latency_ms": 50,
      "buffer_size": 262144,
      "aqm_policy": "fq_codel"
    },
    "dynamic": {
      "ctp_name": "caffeine-mix-2024",
      "ctp_operations": ["extract:dns", "transform:scale=0.5"],
      "ctp_validated": true
    }
  },
  "shaping_state": {
    "substrate_worker_id": "sw-001",
    "tc_applied": true,
    "tc_module": "fq_codel",
    "effective_capacity_mbps": 9.95,
    "effective_rtt_ms": 51
  },
  "progress": {
    "trials_completed": 1,
    "trials_total": 3,
    "current_trial": 2,
    "elapsed_seconds": 125
  }
}
```

**States**:
- `pending` — Created, not yet started
- `provisioning` — CTP validation, Substrate Worker configuration, tc module loading
- `running` — Workflows executing under bottleneck regime
- `complete` — All trials finished, results aggregated
- `failed` — Error occurred (CTP validation, Substrate config, or workflow execution)
- `archived` — Results stored, temporary files cleaned up

---

### 2.5. Batch Create Experiments

**Endpoint**: `POST /experiments/batch`

**Request**:
```json
{
  "experiments": [
    {
      "experiment_id": "youtube-10mbps-ctp-001",
      "capacity_mbps": 10.0,
      "latency_ms": 50,
      "aqm_policy": "fq_codel",
      "ctp_name": "caffeine-mix-2024",
      "ctp_operations": ["extract:dns"],
      "application": "youtube",
      "duration_seconds": 60,
      "num_trials": 3
    },
    {
      "experiment_id": "zoom-25mbps-ctp-001",
      "capacity_mbps": 25.0,
      "latency_ms": 30,
      "aqm_policy": "cake",
      "ctp_name": "office-bg-2024",
      "application": "zoom",
      "duration_seconds": 120,
      "num_trials": 2
    }
  ]
}
```

**Response** (202 Accepted):
```json
{
  "batch_id": "batch-2026-03-04-001",
  "experiments_created": 2,
  "experiments": [
    {"experiment_id": "youtube-10mbps-ctp-001", "status": "pending"},
    {"experiment_id": "zoom-25mbps-ctp-001", "status": "pending"}
  ],
  "status_url": "/batch/batch-2026-03-04-001"
}
```

### 3. List Experiments

**Endpoint**: `GET /experiments`

**Query Parameters**:
- `status` — Filter by status (pending, running, complete, failed)
- `application` — Filter by application (youtube, netflix, zoom)
- `ctp_name` — Filter by CTP
- `aqm_policy` — Filter by queue discipline
- `capacity_min`, `capacity_max` — Filter by capacity range
- `created_after`, `created_before` — Filter by date
- `limit` — Max results (default: 50, max: 500)
- `offset` — Pagination offset (default: 0)

**Response** (200 OK):
```json
{
  "experiments": [
    {
      "experiment_id": "youtube-10mbps-ctp-001",
      "status": "complete",
      "application": "youtube",
      "ctp_name": "caffeine-mix-2024",
      "aqm_policy": "fq_codel",
      "created_at": "2026-03-04T10:00:00Z"
    },
    {
      "experiment_id": "zoom-25mbps-ctp-001",
      "status": "running",
      "application": "zoom",
      "ctp_name": "office-bg-2024",
      "aqm_policy": "cake",
      "created_at": "2026-03-04T11:00:00Z"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

---

### 4. Execute Experiment

**Endpoint**: `POST /experiments/{experiment_id}/execute`

**Request**: (body optional)
```json
{
  "skip_bottleneck_verification": false,
  "capture_pcap": true
}
```

**Response** (202 Accepted):
```json
{
  "experiment_id": "youtube-10mbps-001",
  "status": "provisioning",
  "message": "Experiment execution started",
  "execution_id": "exec-abc123"
}
```

**State Transitions**:
- pending → provisioning (CTP validated)
- provisioning → running (Substrate Worker ready, capture started)
- running → complete (all trials done, results aggregated)

**Error Cases**:
- 400 Bad Request — experiment already executed
- 404 Not Found — experiment_id doesn't exist
- 409 Conflict — bottleneck verification failed
- 503 Service Unavailable — service unreachable

---

### 5. Get Experiment Results

**Endpoint**: `GET /experiments/{experiment_id}/results`

**Response** (200 OK):
```json
{
  "experiment_id": "youtube-10mbps-ctp-001",
  "status": "complete",
  "completed_at": "2026-03-04T10:03:00Z",
  "bottleneck_regime": {
    "static": {
      "capacity_mbps": 10.0,
      "latency_ms": 50,
      "buffer_size": 262144,
      "aqm_policy": "fq_codel"
    },
    "dynamic": {
      "ctp_name": "caffeine-mix-2024",
      "ctp_operations": ["extract:dns", "transform:scale=0.5"]
    }
  },
  "results": [
    {
      "trial_number": 1,
      "status": "success",
      "duration_actual": 61.2,
      "shaping_applied": {
        "tc_module": "fq_codel",
        "measured_capacity": 9.95,
        "measured_rtt": 51.3
      },
      "captures": {
        "pcap_path": "s3://results/youtube-10mbps-ctp-001/trial-1.pcap",
        "tcpdump_filter": "tcp port 443"
      },
      "metrics": {
        "qoe": {
          "startup_time_ms": 2340,
          "mean_bitrate_mbps": 8.8,
          "bitrate_changes": 2,
          "rebuffer_events": 0,
          "rebuffer_duration_ms": 0
        },
        "transport": {
          "throughput_mbps": 9.95,
          "rtt_ms": 51.3,
          "packet_loss": 0.0002,
          "retransmissions": 47
        }
      },
      "analysis": {
        "c_static": {
          "capacity_mbps": 10.0,
          "latency_ms": 50,
          "buffer_size": 262144,
          "aqm_policy": "fq_codel"
        },
        "c_dyn": {
          "ctp_name": "caffeine-mix-2024",
          "ctp_applied": true,
          "measured_capacity": 9.95,
          "measured_rtt": 51.3
        },
        "c_app": {
          "application": "youtube",
          "workflow_spec": "watch-video-60s"
        },
        "c_trans": {
          "protocol": "tcp",
          "congestion_control": "cubic"
        }
      }
    },
    {
      "trial_number": 2,
      "status": "success",
      "duration_actual": 60.8,
      "shaping_applied": {
        "tc_module": "fq_codel",
        "measured_capacity": 9.97,
        "measured_rtt": 50.9
      },
      "captures": {
        "pcap_path": "s3://results/youtube-10mbps-ctp-001/trial-2.pcap"
      },
      "metrics": {
        "qoe": {
          "startup_time_ms": 2280,
          "mean_bitrate_mbps": 8.9,
          "bitrate_changes": 1,
          "rebuffer_events": 0
        },
        "transport": {
          "throughput_mbps": 9.97,
          "rtt_ms": 50.9,
          "packet_loss": 0.0001,
          "retransmissions": 42
        }
      },
      "analysis": {
        "c_static": {
          "capacity_mbps": 10.0,
          "latency_ms": 50,
          "buffer_size": 262144,
          "aqm_policy": "fq_codel"
        },
        "c_dyn": {
          "ctp_name": "caffeine-mix-2024",
          "ctp_applied": true,
          "measured_capacity": 9.97,
          "measured_rtt": 50.9
        },
        "c_app": {
          "application": "youtube",
          "workflow_spec": "watch-video-60s"
        },
        "c_trans": {
          "protocol": "tcp",
          "congestion_control": "cubic"
        }
      }
    }
  ],
  "aggregated_analysis": {
    "mean_startup_time_ms": 2310,
    "mean_bitrate_mbps": 8.85,
    "total_rebuffer_events": 0,
    "mean_packet_loss": 0.00015,
    "fidelity_notes": "Network conditions stable across trials; fq_codel provided consistent fairness"
  }
}
```

---

### 6. Get Substrate Status

**Endpoint**: `GET /status`

**Response** (200 OK):
```json
{
  "status": "operational",
  "timestamp": "2026-03-04T10:30:00Z",
  "services": {
    "ctp_service": {
      "status": "healthy",
      "latency_ms": 12
    },
    "substrate_worker": {
      "status": "healthy",
      "workers_available": 4,
      "workers_in_use": 2,
      "latency_ms": 18
    },
    "netgent_service": {
      "status": "healthy",
      "latency_ms": 25
    },
    "storage_service": {
      "status": "healthy",
      "latency_ms": 35
    }
  },
  "capabilities": {
    "supported_aqm_policies": ["fifo", "codel", "pie", "fq_codel", "cake"],
    "supported_tc_modules": ["tbf", "htb", "qdisc_fq_codel", "qdisc_cake"],
    "supported_applications": ["youtube", "netflix", "zoom", "iperf3"],
    "ctp_repository_size_gb": 142.5
  }
}
```

## Experiment Dataclass (Intent Plane)

The Experiment dataclass maps directly to NetForge planes:

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class BottleneckRegime:
    """Defines the complete bottleneck configuration."""
    static: 'BottleneckStatic'
    dynamic: 'BottleneckDynamic'

@dataclass
class BottleneckStatic:
    """Static bottleneck attributes (Intent Plane)."""
    capacity_mbps: float          # Capacity constraint
    latency_ms: float             # Base latency/RTT
    buffer_size: int              # Queue buffer in bytes
    aqm_policy: str               # Active Queue Management policy

@dataclass
class BottleneckDynamic:
    """Dynamic congestion pressure (Representation Plane)."""
    ctp_name: str                 # Cross-Traffic Profile identifier
    ctp_operations: List[str]     # CTP operations: extract, select, transform, merge, replay
    ctp_validated: bool = False

@dataclass
class Experiment:
    """Full experiment specification (Intent Plane)."""
    experiment_id: str
    # Static bottleneck attributes
    capacity_mbps: float
    latency_ms: float
    buffer_size: int
    aqm_policy: str
    # Dynamic congestion pressure
    ctp_name: str
    ctp_operations: List[str]
    # Application workflow
    application: str
    workflow_spec: str
    duration_seconds: int
    num_trials: int = 1
    capture_pcap: bool = True
    # Metadata and state
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, provisioning, running, complete, failed, archived
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

@dataclass
class BottleneckState:
    """Substrate Worker enforcement result (Execution Plane)."""
    tc_module: str                # tc module applied
    measured_capacity_mbps: float
    measured_rtt_ms: float
    enforcement_success: bool

@dataclass
class ExperimentResult:
    """Complete result from one trial (Representation Plane)."""
    experiment_id: str
    trial_number: int
    status: str                   # success, failure, timeout
    duration_actual: float
    shaping_applied: BottleneckState
    captures: Dict[str, str]      # pcap_path, tcpdump_filter, etc.
    metrics: Dict[str, Any]       # qoe, transport metrics
    analysis: Dict[str, Any]      # c_static, c_dyn, c_app, c_trans
    errors: Optional[List[str]] = None
```

## Service Integration Points

### CTP Service (Representation Plane)
- **Endpoint**: POST `/ctps/validate`
- **Purpose**: Validate CTP name, operations, and transform them into Substrate Worker instructions
- **Inputs**: ctp_name, ctp_operations (extract, select, transform, merge, replay)
- **Outputs**: Validated CTP config, transformed traffic shaping rules
- **Failure Mode**: Return 404 if CTP not found; 400 if operations invalid; return 503 if unavailable

### Substrate Worker (Execution Plane)
- **Endpoint**: POST `/workers/configure`
- **Purpose**: Apply bottleneck regime via tc (traffic control), tshark (capture), tcpreplay (replay)
- **Inputs**: BottleneckStatic, BottleneckDynamic, application config
- **Outputs**: BottleneckState (measured capacity, RTT, enforcement success)
- **Failure Mode**: Return 503 on kernel module unavailability or privilege errors; retry with backoff

### NetGent Service (Application Execution)
- **Endpoint**: POST `/workflows/execute`
- **Purpose**: Execute application workflow (e.g., watch-video-60s) under shaped network conditions
- **Inputs**: application, workflow_spec, duration_seconds, capture settings
- **Outputs**: Metrics (QoE, transport), PCAP path, any errors
- **Failure Mode**: Timeout after 60s; return 504 Gateway Timeout; log partial results

### Storage Service (Archival)
- **Endpoint**: POST `/results/store`
- **Purpose**: Persist ExperimentResult to durable storage (S3, database, etc.)
- **Inputs**: ExperimentResult, metadata, PCAP path
- **Outputs**: Confirmation, archive URL
- **Failure Mode**: Queue in-memory on transient failures; retry async

## Experiment State Machine

```
┌────────────────────────────────────────────────────────────────┐
│           BOTTLENECK EXPERIMENT LIFECYCLE                      │
│       (Intent Plane → Representation Plane → Execution)        │
└────────────────────────────────────────────────────────────────┘

                         ┌─────────────┐
                         │   PENDING   │ (Intent specified)
                         └──────┬──────┘
                                │ execute()
                                ▼
                    ┌──────────────────────────┐
                    │    PROVISIONING          │
                    │ • CTP Service validate   │
                    │ • Substrate config       │
                    │ • tc module load         │
                    │ • tshark prep            │
                    └─────┬────────────────────┘
                          │ success
                          ▼
                    ┌──────────────────────────┐
                    │      RUNNING             │
                    │ • NetGent workflow exec  │
                    │ • Capture PCAP (tshark)  │
                    │ • CTP replay (tcpreplay) │
                    │ • Trial loop (N times)   │
                    └─────┬────────────────────┘
                          │ all_trials_done
                          ▼
                    ┌──────────────────────────┐
                    │      COMPLETE            │
                    │ • Aggregate results      │
                    │ • Build ExperimentResult │
                    │ • Queue storage          │
                    └─────┬────────────────────┘
                          │ storage_confirmed
                          ▼
                    ┌──────────────────────────┐
                    │      ARCHIVED            │
                    │ • Clean Substrate state  │
                    │ • Release resources      │
                    └──────────────────────────┘

        FAILURE TRANSITIONS (from any state):
        error → FAILED → retry_or_discard

        Retry allowed from: pending, provisioning, running
        No retry from: archived
```

## Quality Attributes

The Experiment API must enforce four core requirements:

1. **Controllability**: Users precisely specify bottleneck regime (static + dynamic) and observe enforcement via BottleneckState
2. **Composability**: Multiple CTP operations can be chained; experiments are independent and parallelizable
3. **Fidelity**: Measured network conditions (throughput, RTT) must match configured regime within 5% tolerance
4. **Replicability**: Same experiment_id + CTP + bottleneck regime produces consistent results across runs

## Testing Strategy

### Unit Tests
- Experiment creation with valid/invalid bottleneck regime (static + dynamic)
- State machine transitions (valid and invalid)
- CTP operation validation (extract, select, transform, merge, replay)
- BottleneckStatic constraint validation (capacity > 0, buffer > 0, latency >= 0)
- Dataclass serialization/deserialization (Experiment, ExperimentResult)

### Integration Tests
- Full lifecycle: create → provision (CTP validate + Substrate config) → run (NetGent workflow) → complete (aggregate results) → archive
- CTP Service integration: invalid CTP name → 404, valid CTP → 200 with transformed rules
- Substrate Worker integration: tc module load, measured capacity/RTT within 5% of configured
- NetGent Service integration: workflow execution under shaped conditions
- Storage Service integration: ExperimentResult persisted, archive URL returned
- Batch experiments: multiple experiments run concurrently without interference
- Query filtering: by status, application, ctp_name, aqm_policy, capacity range
- Error handling: transient failures (503) trigger retry; persistent failures (400, 404) surface to client

### Fidelity Tests
- Configure 10Mbps capacity → measured throughput 9.5–10.5 Mbps across trials
- Configure 50ms latency → measured RTT 47.5–52.5 ms across trials
- fq_codel AQM → packet loss < 0.1%, fair queue distribution across flows
- CTP replay active → cross-traffic present in PCAP, throughput reduced proportionally

### Replication Tests
- Repeat same experiment_id with identical bottleneck regime → metrics within 2% variance
- Deterministic workflow (e.g., fetch N bytes) → identical output across runs (PCAP length, flow count)

## Implementation Notes

### Track A (Monolithic, Clean Interfaces)
- Single process with internal orchestration logic
- Clear service clients (CTPClient, SubstrateClient, NetGentClient, StorageClient)
- In-memory experiment store with thread-safe concurrent access
- Returns fully-formed ExperimentResult with all metrics and analysis
- **Jaber delivers working code first via Track A**

### Track B (SOA Scaffolding)
- Service boundaries outlined but not yet enforced
- Async task queue for long-running orchestration (celery/RQ optional)
- Future: extract orchestrator into separate service if scaling required
- **Jaber not forced into SOA; Track A is the priority**

### Project Structure

```
services/experiment-api/
├── Dockerfile
├── docker-compose.yml      # Local dev: api + ctp + substrate + netgent + storage
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py             # Flask app factory
│   ├── api/
│   │   ├── __init__.py
│   │   ├── experiments.py  # Route handlers: POST/GET /experiments, /batch
│   │   └── status.py       # GET /status (substrate health)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py      # Dataclass definitions + JSON schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── orchestrator.py # run_experiment(Experiment) → ExperimentResult
│   │   └── state_machine.py
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── ctp_client.py        # validate_ctp(), get_ctp_config()
│   │   ├── substrate_client.py  # configure(), start_capture(), stop_capture()
│   │   ├── netgent_client.py    # execute_workflow()
│   │   └── storage_client.py    # store_result()
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       └── validation.py    # Validate bottleneck regime, CTP operations
└── tests/
    ├── __init__.py
    ├── test_api.py
    ├── test_orchestration.py
    ├── test_state_machine.py
    └── fixtures/            # Mock responses from CTP, Substrate, NetGent
```

### Orchestrator Interface

```python
class NetReplicaController:
    async def run_experiment(self, experiment: Experiment) -> ExperimentResult:
        """Execute single experiment under bottleneck regime."""
        # State: pending → provisioning (CTP validate + Substrate config)
        # State: provisioning → running (NetGent workflow loop over trials)
        # State: running → complete (aggregate results)
        # Return: ExperimentResult with metrics, captures, analysis

    async def run_batch(self, experiments: List[Experiment]) -> List[ExperimentResult]:
        """Execute multiple experiments concurrently (parallelizable)."""
        # Parallelism: up to substrate_worker pool size
        # Each experiment is independent (own bottleneck regime, CTP, trial set)

    async def get_status(self) -> Dict[str, Any]:
        """Substrate and service health."""
        # Returns: services health, capabilities, resource utilization
```

### Key Implementation Decisions

1. **In-Memory Store**: experiments_db keyed by experiment_id; thread-safe with locks
2. **Synchronous API**: Flask request/response cycle; long-running ops (run_experiment) handled inline with timeouts
3. **Error Handling**: CTP validation errors (400) fail fast; Substrate errors (503) retry 3x with backoff
4. **PCAP Capture**: tshark capture initiated in Substrate Worker; path returned in ExperimentResult.captures
5. **Metrics Aggregation**: Per-trial metrics collected; aggregated_analysis computed on GET /results
6. **Replication**: Deterministic order of operations ensures consistent results with same bottleneck regime

## Deployment & Development

### Local Development (Docker Compose)

```yaml
version: '3.8'
services:
  experiment-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      CTP_SERVICE_URL: http://ctp-service:8001
      SUBSTRATE_WORKER_URL: http://substrate-worker:8002
      NETGENT_SERVICE_URL: http://netgent-service:8003
      STORAGE_SERVICE_URL: http://storage-service:8004
    depends_on:
      - ctp-service
      - substrate-worker
      - netgent-service
      - storage-service

  ctp-service:
    image: ctp-service:latest
    ports:
      - "8001:8001"

  substrate-worker:
    image: substrate-worker:latest
    ports:
      - "8002:8002"
    privileged: true  # For tc (traffic control)

  netgent-service:
    image: netgent-service:latest
    ports:
      - "8003:8003"

  storage-service:
    image: storage-service:latest
    ports:
      - "8004:8004"
```

### Production Deployment
- Kubernetes Deployment with rolling updates
- Service mesh (Istio) for inter-service communication
- Distributed tracing (Jaeger) for experiment execution observability
- Metrics export (Prometheus) for capacity monitoring

### Running Tests

```bash
# Unit tests
pytest tests/test_api.py -v

# Integration tests (requires docker-compose running)
pytest tests/test_orchestration.py -v

# Fidelity tests (measure actual network conditions)
pytest tests/test_fidelity.py -v --tb=short
```

## Acknowledgments

- **Jaber**: Lead design and implementation (Track A + Track B scaffolding)
- **Prof. Arpit Gupta**: PI, NetForge three-plane architecture guidance
- **D1 Collaborators**: CTP Service, Substrate Worker, NetGent Service teams

---

**Deliverable**: D1 (Network Virtualization Substrate - Intent Plane)
**Last Updated**: 2026-03-04
**Status**: Specification Ready (Implementation by Jaber, Week 1–3)
**Quality Attributes**: Controllability, Composability, Fidelity, Replicability
