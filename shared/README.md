# Shared Code and Contracts

This directory contains common code, dataclass definitions, and HTTP client utilities shared across all services. It implements the three-plane architecture (Intent, Representation, Execution) for the agentic thin waist networking framework.

## Structure

```
shared/
├── README.md                    # This file
├── models/
│   ├── __init__.py
│   ├── experiment.py           # Experiment, ExperimentResult, SuccessMetric, AnalysisResult
│   ├── network.py              # BottleneckState, NetReplicaConfig
│   ├── ctp.py                  # CTP-related dataclasses
│   ├── workflow.py             # WorkflowResult, QoEMetrics
│   └── README.md               # Complete model reference
│
├── clients/
│   ├── __init__.py
│   ├── base.py                 # BaseHTTPClient
│   ├── experiment_api.py       # ExperimentAPIClient (port 8000)
│   ├── ctp_service.py          # CTPServiceClient (port 8001)
│   ├── substrate_worker.py     # SubstrateWorkerClient (port 8002)
│   ├── netgent_service.py      # NetGentServiceClient (port 8003)
│   ├── storage_service.py      # TelemetryServiceClient (port 8004)
│   └── README.md               # Complete client API reference
│
└── constants.py                # Shared constants, enums, port definitions
```

## Architecture Context

The agentic thin waist separates concerns into three orthogonal planes:

**Intent Plane (Link, Bottleneck)**:
- Users express networking intents via Link() and Bottleneck() abstractions
- Bottleneck regime = static bottleneck attributes + dynamic congestion pressure
- Static attributes: capacity, base latency, buffering, queue management (AQM)
- Dynamic pressure: Cross-Traffic Profiles (CTPs) — temporal structure of aggregate demand

**Representation Plane (CrossTraffic, CTPs)**:
- CTP (Cross-Traffic Profile) captures and manipulates demand patterns
- CTP operations: extract(), select(), transform(), merge(), replay()
- Stored as reusable, composable artifacts

**Execution Plane (tc, tshark, tcpreplay)**:
- Linux traffic control (tc) applies bottlenecks
- Packet capture via tshark
- Traffic replay via tcpreplay

## Models Documentation

All dataclass definitions are in the `models/` directory. These are the single source of truth for all service-to-service contracts.

### Key Dataclasses

**Experiment Lifecycle**:
- `Experiment` — Complete specification with Intent Plane (Link, Bottleneck), Representation Plane (CTP), application, and success metrics
- `ExperimentResult` — Trial results including BottleneckState verification, captures, computed metrics, and analysis
- `SuccessMetric` — Threshold-based success criteria (name, source, direction, threshold)
- `AnalysisResult` — Post-experiment analysis with computed metrics, threshold evaluation, anomalies, raw data paths

**Bottleneck Configuration**:
- `BottleneckState` — Verification of static attributes (capacity, latency, buffering, AQM) against measured conditions
- `NetReplicaConfig` — Complete network replica specification for deployment

**CTP and Traffic**:
- Dataclasses for CTP metadata, selection, transformation operations

**Workflows**:
- `WorkflowResult` — Application workflow execution results from NFA execution
- `QoEMetrics` — Per-application quality metrics

See `models/README.md` for complete specifications.

## Clients Documentation

HTTP client utilities for service-to-service communication. All clients:
- Inherit from `BaseHTTPClient` for common functionality
- Implement timeout and retry logic
- Log all requests/responses
- Raise descriptive exceptions on failure

Service clients map to the netUnicorn SOA architecture:

**Core Services**:
- `ExperimentAPIClient` (port 8000) — Experiment API service
- `CTPServiceClient` (port 8001) — CTP Service (Representation Plane)
- `SubstrateWorkerClient` (port 8002) — Execution substrate worker
- `NetGentServiceClient` (port 8003) — NetGent (Application execution)
- `TelemetryServiceClient` (port 8004) — Datastore service

### Using Clients

```python
from shared.clients import ExperimentAPIClient, CTPServiceClient

# Create clients pointing to service URLs
exp_api = ExperimentAPIClient("http://experiment-api:8000")
ctp_svc = CTPServiceClient("http://ctp-service:8001")

# Call methods; exceptions are raised on error
try:
    result = exp_api.create_experiment({
        "experiment_id": "youtube-10mbps-001",
        "download_mbps": 10,
        "upload_mbps": 5,
        "latency_ms": 50,
        "application": "youtube",
        "duration_seconds": 60
    })
    print(f"Created experiment: {result['experiment_id']}")
except Exception as e:
    print(f"Error: {e}")
```

See `clients/README.md` for complete API documentation.

## Constants and Enums

```python
# shared/constants.py

SUPPORTED_APPLICATIONS = [
    "youtube", "netflix", "zoom", "twitch", "discord",
    "google-meet", "skype", "teams"
]

class AQMPolicy(str, Enum):
    FIFO = "fifo"
    CODEL = "codel"
    PIE = "pie"
    FQ_CODEL = "fq_codel"
    SFQ = "sfq"

class ExperimentStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    ARCHIVED = "archived"

# Port assignments
EXPERIMENT_API_PORT = 8000
CTP_SERVICE_PORT = 8001
SUBSTRATE_WORKER_PORT = 8002
NETGENT_SERVICE_PORT = 8003
STORAGE_SERVICE_PORT = 8004
ORCHESTRATION_PORT = 8005
```

## Import Examples

```python
# Import dataclasses
from shared.models import (
    Experiment,
    ExperimentResult,
    SuccessMetric,
    AnalysisResult,
    BottleneckState,
    NetReplicaConfig,
    WorkflowResult,
    QoEMetrics
)

# Import clients
from shared.clients import (
    ExperimentAPIClient,
    CTPServiceClient,
    SubstrateWorkerClient,
    NetGentServiceClient,
    TelemetryServiceClient
)

# Import constants
from shared.constants import (
    SUPPORTED_APPLICATIONS,
    AQMPolicy,
    ExperimentStatus
)
```

## Development Guidelines

1. **Define contracts in shared/models** — All dataclass definitions belong here
2. **Use dataclasses, not dicts** — Ensures type safety and IDE support
3. **Keep clients thin** — Just HTTP wrappers; business logic in services
4. **Use correct terminology** — CTP (Cross-Traffic Profile), not CTC; Bottleneck regime = static attributes + dynamic pressure
5. **Document fields** — Every field should have a docstring explaining its purpose
6. **Version dataclasses** — If you change a schema, add a new version (e.g., ExperimentV2)

## Testing Shared Code

```bash
# Run shared code tests
pytest shared/tests/

# Or from the root:
pytest tests/test_shared_models.py
pytest tests/test_shared_clients.py
```

## Migration Strategy

When updating dataclass schemas:

1. Define the new dataclass (e.g., `ExperimentV2`) in `models/experiment.py`
2. Add a migration function: `def migrate_experiment_v1_to_v2(v1: Experiment) -> ExperimentV2`
3. Update services to accept both versions (for backwards compatibility)
4. After all services updated, deprecate V1

## Team and Acknowledgments

**Principal Investigator**: Prof. Arpit Gupta

**Team**: Jaber, Eugene, Haarika, Manni, Sylee

**Reference Implementation**: OpenClaw (real private SNL-UCSB orchestration framework)

---

**Last Updated**: 2026-03-04
**Status**: Architecture Phase
**Next Milestone**: Implementation of dataclasses (Week 1)
