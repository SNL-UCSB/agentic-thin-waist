# Shared Code and Contracts

This directory contains common code, dataclass definitions, and HTTP client utilities shared across all services.

## Structure

```
shared/
├── README.md                    # This file
├── models/
│   ├── __init__.py
│   ├── experiment.py           # Experiment, ExperimentResult dataclasses
│   ├── network.py              # BottleneckState, NetReplicaConfig dataclasses
│   ├── ctp.py                  # CTP-related dataclasses
│   ├── workflow.py             # WorkflowResult, QoEMetrics dataclasses
│   └── README.md
│
├── clients/
│   ├── __init__.py
│   ├── base.py                 # BaseHTTPClient
│   ├── experiment_api.py       # ExperimentAPIClient
│   ├── ctp_service.py          # CTPServiceClient
│   ├── substrate_worker.py     # SubstrateWorkerClient
│   ├── storage_service.py      # StorageServiceClient
│   ├── netgent_service.py      # NetGentServiceClient
│   └── README.md
│
└── constants.py                # Shared constants, enums
```

## Models Documentation

All dataclass definitions are in the `models/` directory. These are the single source of truth for all service-to-service contracts.

### Key Dataclasses

**Experiment Lifecycle**:
- `Experiment` — Full specification with capacity, latency, application, duration
- `ExperimentResult` — Results with pcap paths, QoE metrics, bottleneck state
- `ContextualTreeNode` — Rich tagging for results (c_static, c_dyn, c_app, c_trans)

**Network Configuration**:
- `NetReplicaConfig` — CTP specification (capacity, latency, loss, AQM)
- `BottleneckState` — Measured network conditions (configured vs measured)

**Workflows**:
- `WorkflowResult` — Application workflow execution results
- `QoEMetrics` — Video startup time, bitrate, rebuffer events, etc.

See `models/README.md` for complete specifications.

## Clients Documentation

HTTP client utilities for service-to-service communication. All clients:
- Inherit from `BaseHTTPClient` for common functionality
- Implement timeout and retry logic
- Log all requests/responses
- Raise descriptive exceptions on failure

### Using Clients

```python
from shared.clients import ExperimentAPIClient, CTCServiceClient

# Create clients pointing to service URLs
exp_api = ExperimentAPIClient("http://experiment-api:8000")
ctp_svc = CTCServiceClient("http://ctp-service:8001")

# Call methods; exceptions are raised on error
try:
    result = exp_api.create_experiment(
        experiment_id="youtube-10mbps-001",
        capacity_mbps=10,
        latency_ms=50,
        application="youtube",
        duration_seconds=60
    )
    print(f"Created experiment: {result.experiment_id}")
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
    StorageServiceClient,
    NetGentServiceClient
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
4. **Version dataclasses** — If you change a schema, add a new version (e.g., ExperimentV2)
5. **Document fields** — Every field should have a docstring explaining its purpose

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

---

**Last Updated**: 2026-03-04
**Status**: Architecture Phase
**Next Milestone**: Implementation of dataclasses (Week 1)
