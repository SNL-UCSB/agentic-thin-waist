# Experiment API Service

**Port**: 8000
**Deliverable**: D1 (Network Virtualization Substrate - Intent Plane)
**Priority**: CRITICAL
**Status**: To be implemented

## Purpose

The Experiment API is the central orchestration service that manages the complete lifecycle of network research experiments. It acts as the interface between researchers (or the Orchestration service) and the infrastructure services (CTP, Substrate, NetGent, Storage). The Experiment API is responsible for:

1. **Experiment lifecycle management**: Create, validate, schedule, execute, and archive experiments
2. **Service orchestration**: Coordinate calls to CTP Service, Substrate Worker, NetGent Service, and Storage Service
3. **State machine enforcement**: Ensure experiments follow the correct state transitions
4. **Bottleneck verification**: Confirm that network conditions are applied before running workflows
5. **Result aggregation**: Collect and merge results from multiple services into a unified response

The Experiment API is the "smart orchestrator" that understands how all the pieces fit together.

## Architecture

```
┌─────────────────────────────────────┐
│    Orchestration Service (8005)     │
│    or Direct HTTP Client            │
└────────────┬────────────────────────┘
             │ POST /experiments
             ▼
┌─────────────────────────────────────┐
│   EXPERIMENT API (8000)             │
│  ┌──────────────────────────────┐   │
│  │ Experiment State Machine     │   │
│  │ pending→provisioning→running │   │
│  │ →complete→archived           │   │
│  └──────────────────────────────┘   │
└────┬────────┬────────┬──────────────┘
     │        │        │
     ▼        ▼        ▼
 ┌───────┐ ┌────────┐ ┌─────────┐
 │CTP    │ │Substrate│ │ NetGent │
 │:8001  │ │:8002   │ │ :8003   │
 └────┬──┘ └───┬────┘ └────┬────┘
      │        │           │
      └────────┼───────────┘
              │ results
              ▼
     ┌────────────────────┐
     │Storage Service:8004│
     └────────────────────┘
```

## API Specification

### 1. Create Experiment

**Endpoint**: `POST /experiments`

**Request**:
```json
{
  "experiment_id": "youtube-10mbps-001",
  "capacity_mbps": 10.0,
  "latency_ms": 50,
  "loss_rate": 0.0,
  "aqm_policy": "fifo",
  "application": "youtube",
  "duration_seconds": 30,
  "num_trials": 1,
  "metadata": {
    "researcher": "john@example.com",
    "study": "broadband-characterization"
  }
}
```

**Response** (201 Created):
```json
{
  "experiment_id": "youtube-10mbps-001",
  "status": "pending",
  "created_at": "2026-03-04T10:00:00Z",
  "estimated_duration_seconds": 30,
  "_links": {
    "self": "/experiments/youtube-10mbps-001",
    "execute": "/experiments/youtube-10mbps-001/execute",
    "results": "/experiments/youtube-10mbps-001/results"
  }
}
```

**Validation**:
- capacity_mbps > 0
- latency_ms >= 0
- loss_rate in [0, 1]
- aqm_policy in ["fifo", "codel", "pie", "fq_codel"]
- application in list of supported apps (see `/workflows/available`)
- duration_seconds > 0
- experiment_id is unique

**Error Codes**:
- 400 Bad Request — validation failed
- 409 Conflict — experiment_id already exists
- 503 Service Unavailable — backend service unreachable

---

### 2. Get Experiment Status

**Endpoint**: `GET /experiments/{experiment_id}`

**Response** (200 OK):
```json
{
  "experiment_id": "youtube-10mbps-001",
  "status": "running",
  "created_at": "2026-03-04T10:00:00Z",
  "started_at": "2026-03-04T10:00:05Z",
  "bottleneck_state": {
    "configured_capacity": 10.0,
    "configured_latency": 50,
    "measured_throughput": 9.8,
    "measured_rtt": 52,
    "verification_passed": true
  },
  "progress": {
    "trials_completed": 0,
    "trials_total": 1,
    "elapsed_seconds": 5
  }
}
```

**States**:
- `pending` — Created, not yet started
- `provisioning` — Validating CTP, preparing Substrate Worker
- `running` — Executing workflows
- `complete` — All trials finished
- `failed` — Error occurred during execution
- `archived` — Results stored, cleaned up temporary files

---

### 3. List Experiments

**Endpoint**: `GET /experiments`

**Query Parameters**:
- `status` — Filter by status (pending, running, complete, failed)
- `application` — Filter by application (youtube, netflix, zoom, etc.)
- `capacity_min`, `capacity_max` — Filter by capacity range
- `created_after`, `created_before` — Filter by date
- `limit` — Max results (default: 50, max: 500)
- `offset` — Pagination offset (default: 0)

**Response** (200 OK):
```json
{
  "experiments": [
    {
      "experiment_id": "youtube-10mbps-001",
      "status": "complete",
      "created_at": "2026-03-04T10:00:00Z"
    },
    {
      "experiment_id": "zoom-25mbps-001",
      "status": "running",
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
  "experiment_id": "youtube-10mbps-001",
  "status": "complete",
  "completed_at": "2026-03-04T10:00:35Z",
  "results": [
    {
      "trial_number": 1,
      "bottleneck_state": {
        "configured_capacity": 10.0,
        "configured_latency": 50,
        "measured_throughput": 9.8,
        "measured_rtt": 52,
        "verification_passed": true
      },
      "pcap_path": "s3://results/youtube-10mbps-001/trial-1.pcap",
      "qoe_metrics": {
        "video_startup_time_ms": 2500,
        "mean_bitrate_mbps": 8.5,
        "bitrate_changes": 3,
        "rebuffer_events": 1,
        "rebuffer_duration_ms": 2000
      },
      "transport_state": {
        "throughput_mbps": 9.8,
        "rtt_ms": 52,
        "packet_loss": 0.001,
        "retransmissions": 125
      },
      "contextual_tree": {
        "c_static": {
          "capacity_mbps": 10.0,
          "latency_ms": 50,
          "buffer_size": null,
          "aqm_policy": "fifo"
        },
        "c_dyn": {
          "ctp_cluster_id": "ctp-001",
          "measured_throughput": 9.8,
          "measured_rtt": 52
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
  "aggregated_qoe": {
    "avg_video_startup_time_ms": 2500,
    "avg_mean_bitrate_mbps": 8.5,
    "total_rebuffer_events": 1
  }
}
```

---

### 6. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "services": {
    "ctp_service": "healthy",
    "substrate_worker": "healthy",
    "netgent_service": "healthy",
    "storage_service": "healthy"
  },
  "timestamp": "2026-03-04T10:00:00Z"
}
```

## Dataclass Contracts

All request/response bodies use these dataclasses (defined in `shared/models/`):

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class Experiment:
    """Full experiment specification and state."""
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float = 0.0
    aqm_policy: str = "fifo"
    application: str
    duration_seconds: int
    num_trials: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, provisioning, running, complete, failed, archived
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

@dataclass
class BottleneckState:
    """Network condition verification."""
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    verification_passed: bool

@dataclass
class ExperimentResult:
    """Complete result from one trial."""
    experiment_id: str
    trial_number: int
    bottleneck_state: BottleneckState
    pcap_path: str
    qoe_metrics: Dict[str, Any]
    transport_state: Dict[str, Any]
    contextual_tree: 'ContextualTreeNode'
    status: str  # "success", "failure", "timeout"
    error: Optional[str] = None

@dataclass
class ContextualTreeNode:
    """Rich metadata tagging for results."""
    c_static: Dict[str, Any]  # capacity, latency, buffer, aqm
    c_dyn: Dict[str, Any]      # measured network state
    c_app: Dict[str, Any]      # application, workflow
    c_trans: Dict[str, Any]    # protocol, cc algorithm
```

## Service Dependencies

| Service | Endpoint | Purpose | Failure Mode |
|---------|----------|---------|--------------|
| CTP Service | POST /ctps/validate | Validate network config | Return 400 to client |
| Substrate Worker | POST /workers/configure | Apply network conditions | Return 503, retry |
| NetGent Service | POST /workflows/execute | Run application workflow | Timeout after 60s |
| Storage Service | POST /results | Store results | Queue in-memory, retry |

## State Machine

```
┌──────────────────────────────────────────────────────────┐
│                    EXPERIMENT LIFECYCLE                  │
└──────────────────────────────────────────────────────────┘

                        ┌─────────────┐
                        │   PENDING   │
                        └──────┬──────┘
                               │ execute()
                               ▼
                        ┌──────────────────┐
                        │  PROVISIONING    │
                        │ CTP validation   │
                        │ Substrate ready  │
                        └─────┬────────────┘
                              │ success
                              ▼
                        ┌─────────────┐
                        │  RUNNING    │
                        │ workflows   │
                        │ executing   │
                        └─────┬───────┘
                              │ trials_complete
                              ▼
                        ┌─────────────┐
                        │  COMPLETE   │
                        └─────┬───────┘
                              │ results_stored
                              ▼
                        ┌─────────────┐
                        │  ARCHIVED   │
                        └─────────────┘

        FAILURE TRANSITIONS (from any state):
        error() → FAILED → can retry or discard
```

## Testing Criteria

### Unit Tests
- Experiment creation with valid/invalid parameters
- State transition validation
- Dataclass serialization/deserialization

### Integration Tests
- Full experiment lifecycle: create → execute → complete
- Bottleneck verification passes for valid CTPs
- Result aggregation from multiple services
- Health check detects unavailable services
- Concurrent experiment execution (multiple experiment_ids)
- Query filtering by status, application, capacity, date

### Performance Tests
- 100 experiments can be stored in-memory without issues
- Response time < 100ms for status queries
- Create experiment < 50ms

## Implementation Guide

### Step 1: Project Structure
```bash
services/experiment-api/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py              # Flask app factory
│   ├── api/
│   │   ├── __init__.py
│   │   ├── experiments.py   # Route handlers
│   │   └── health.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── experiment.py    # Dataclass definitions (or import from shared/)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── orchestrator.py  # Core orchestration logic
│   │   └── state_machine.py
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── ctp_client.py
│   │   ├── substrate_client.py
│   │   ├── netgent_client.py
│   │   └── storage_client.py
│   └── utils/
│       ├── __init__.py
│       └── logging.py
└── tests/
    ├── __init__.py
    ├── test_api.py
    ├── test_state_machine.py
    └── test_orchestration.py
```

### Step 2: Flask Setup
```python
# app/main.py
from flask import Flask
from app.api import experiments_bp, health_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(experiments_bp)
    app.register_blueprint(health_bp)
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8000)
```

### Step 3: Experiment Store
```python
# In-memory store with thread-safe access
experiments_db = {}  # {experiment_id: Experiment}

def create_experiment(spec: Experiment) -> Experiment:
    if spec.experiment_id in experiments_db:
        raise ValueError("Experiment already exists")
    spec.status = "pending"
    spec.created_at = datetime.utcnow().isoformat()
    experiments_db[spec.experiment_id] = spec
    return spec
```

### Step 4: State Machine
```python
# app/services/state_machine.py
class ExperimentStateMachine:
    VALID_TRANSITIONS = {
        "pending": ["provisioning"],
        "provisioning": ["running", "failed"],
        "running": ["complete", "failed"],
        "complete": ["archived"],
        "failed": ["pending"],  # allow retry
        "archived": []
    }

    def transition(self, current: str, next: str) -> bool:
        return next in self.VALID_TRANSITIONS.get(current, [])
```

### Step 5: Service Clients
```python
# app/clients/ctp_client.py
import requests

class CTPClient:
    def __init__(self, base_url: str = "http://ctp-service:8001"):
        self.base_url = base_url

    def validate_ctp(self, capacity: float, latency: float) -> dict:
        response = requests.post(
            f"{self.base_url}/ctps/validate",
            json={"capacity_mbps": capacity, "latency_ms": latency},
            timeout=5
        )
        return response.json()
```

### Step 6: Orchestration Logic
```python
# app/services/orchestrator.py
class Orchestrator:
    def __init__(self, ctp_client, substrate_client,
                 netgent_client, storage_client):
        self.ctp = ctp_client
        self.substrate = substrate_client
        self.netgent = netgent_client
        self.storage = storage_client

    async def execute_experiment(self, experiment: Experiment):
        # 1. Validate CTP
        # 2. Configure Substrate Worker
        # 3. Start telemetry collection
        # 4. Execute NetGent workflow
        # 5. Collect results
        # 6. Store in Storage Service
        pass
```

### Step 7: Error Handling
- Use try/except around service calls
- Return 503 if dependency unavailable
- Log all errors to stdout
- Implement retry logic with exponential backoff

### Step 8: Tests
```python
# tests/test_api.py
import pytest
from app.main import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()

def test_create_experiment(client):
    response = client.post('/experiments', json={
        "experiment_id": "test-001",
        "capacity_mbps": 10,
        "latency_ms": 50,
        "application": "youtube",
        "duration_seconds": 30
    })
    assert response.status_code == 201
```

## References

- Flask documentation: https://flask.palletsprojects.com/
- Requests library: https://requests.readthedocs.io/
- Python asyncio: https://docs.python.org/3/library/asyncio.html
- NetUnicorn orchestration: https://github.com/Aritro-BhumitraX/NetUnicorn
- REST API design: https://restfulapi.net/

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
