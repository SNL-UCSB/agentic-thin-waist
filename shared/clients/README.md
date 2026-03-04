# HTTP Client Utilities

This directory contains thin HTTP client wrappers for service-to-service communication within the netUnicorn SOA. All clients inherit from `BaseHTTPClient` for common functionality like retry logic and timeout handling.

Service clients map to the agentic thin waist microservices:

| Service | Port | Client | Purpose |
|---------|------|--------|---------|
| Experiment API | 8000 | ExperimentAPIClient | Orchestration and experiment lifecycle |
| CTP Service | 8001 | CTPServiceClient | Cross-Traffic Profile operations (Representation Plane) |
| Substrate Worker | 8002 | SubstrateWorkerClient | Network bottleneck execution (tc, capture) |
| NetGent Service | 8003 | NetGentServiceClient | Application execution (NFA, workflows) |
| Storage Service | 8004 | StorageServiceClient | Datastore for results and artifacts |

## Base Client

**Location**: `base.py`

```python
class BaseHTTPClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, endpoint: str, params: dict = None) -> dict:
        """GET request with retry logic."""
        # Implemented in subclass methods

    def post(self, endpoint: str, json: dict = None) -> dict:
        """POST request with retry logic."""

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Execute request with retries and error handling."""
        # Retries on 503, 504, connection errors
        # Raises HTTPException on client/server errors
        # Logs all requests/responses
```

**Common Features**:
- Automatic retry with exponential backoff (3 retries)
- Configurable timeout (default 10 seconds)
- Request/response logging with correlation IDs
- Proper exception handling with descriptive error messages

## Client Classes

### ExperimentAPIClient

**Port**: 8000

```python
class ExperimentAPIClient(BaseHTTPClient):
    def create_experiment(self, experiment: dict) -> dict:
        """POST /experiments"""

    def get_experiment(self, experiment_id: str) -> dict:
        """GET /experiments/{experiment_id}"""

    def list_experiments(self, status: str = None, limit: int = 50) -> dict:
        """GET /experiments?status=...&limit=..."""

    def execute_experiment(self, experiment_id: str) -> dict:
        """POST /experiments/{experiment_id}/execute"""

    def get_results(self, experiment_id: str) -> dict:
        """GET /experiments/{experiment_id}/results"""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import ExperimentAPIClient

client = ExperimentAPIClient("http://experiment-api:8000")
result = client.create_experiment({
    "experiment_id": "youtube-10mbps-001",
    "capacity_mbps": 10,
    "latency_ms": 50,
    "application": "youtube",
    "duration_seconds": 60
})
print(result["experiment_id"])
```

---

### CTPServiceClient

**Port**: 8001 | **Plane**: Representation

Manages Cross-Traffic Profile (CTP) operations for the Representation Plane. CTPs are reusable demand artifacts that capture temporal patterns of network traffic.

```python
class CTPServiceClient(BaseHTTPClient):
    def validate_ctp(self, ctp: dict) -> dict:
        """POST /ctps/validate - Validate CTP syntax and constraints"""

    def extract_ctp(self, pcap_path: str, name: str) -> dict:
        """POST /ctps/extract - Extract CTP from pcap artifact"""

    def select_ctp(self, ctp_name: str, time_window: dict) -> dict:
        """POST /ctps/select - Select subset of CTP for replay"""

    def transform_ctp(self, ctp: dict, operations: list) -> dict:
        """POST /ctps/transform - Apply CTP operations (scale, filter, etc.)"""

    def merge_ctp(self, ctp_names: list) -> dict:
        """POST /ctps/merge - Combine multiple CTPs"""

    def replay_ctp(self, ctp_name: str, interface: str) -> dict:
        """POST /ctps/replay - Replay CTP via tcpreplay on interface"""

    def get_presets(self) -> dict:
        """GET /ctps/presets - List available CTP presets"""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import CTPServiceClient

client = CTPServiceClient("http://ctp-service:8001")

# Validate a CTP specification
valid = client.validate_ctp({
    "ctp_name": "web-browsing-2024",
    "download_mbps": 10,
    "latency_ms": 50
})

# Extract CTP from captured traffic
ctp = client.extract_ctp(
    pcap_path="/data/traffic.pcap",
    name="extracted-web-browsing"
)

# Replay CTP on an interface for testing
replay_result = client.replay_ctp(
    ctp_name="web-browsing-2024",
    interface="eth0"
)
```

**CTP Operations**:
- `extract()` — Extract demand pattern from pcap
- `select()` — Select time window or traffic subset
- `transform()` — Scale, filter, or modify patterns
- `merge()` — Combine multiple profiles
- `replay()` — Replay via tcpreplay on target interface

---

### SubstrateWorkerClient

**Port**: 8002

```python
class SubstrateWorkerClient(BaseHTTPClient):
    def configure(self, interface: str, tc_commands: list) -> dict:
        """POST /workers/configure"""

    def get_status(self, interface: str = "eth0") -> dict:
        """GET /workers/status?interface=..."""

    def capture_start(self, interface: str, filter: str = "") -> dict:
        """POST /workers/capture/start"""

    def capture_stop(self, capture_id: str, move_to: str = None) -> dict:
        """POST /workers/capture/stop"""

    def get_metrics(self, interface: str = "eth0", duration: int = 10) -> dict:
        """GET /workers/metrics?interface=...&duration=..."""

    def reset(self, interface: str = "eth0") -> dict:
        """POST /workers/reset"""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import SubstrateWorkerClient

worker = SubstrateWorkerClient("http://substrate-worker:8002")

# Apply network config
config = worker.configure("eth0", [
    "tc qdisc replace dev eth0 root handle 1: tbf rate 10mbit burst 15k latency 50ms",
    "tc qdisc add dev eth0 parent 1: handle 10: fifo limit 1000"
])

# Start packet capture
capture = worker.capture_start("eth0")
capture_id = capture["capture_id"]

# ... experiment runs ...

# Stop capture
result = worker.capture_stop(capture_id, move_to="/data/pcaps/test.pcap")
print(f"Captured {result['packets_captured']} packets")
```

---

### NetGentServiceClient

**Port**: 8003

```python
class NetGentServiceClient(BaseHTTPClient):
    def list_workflows(self) -> dict:
        """GET /workflows/available"""

    def compile_workflow(self, nfa_spec: dict) -> dict:
        """POST /workflows/compile"""

    def execute_workflow(self, workflow_id: str, experiment_id: str,
                        timeout: int = 120) -> dict:
        """POST /workflows/execute"""

    def get_workflow_status(self, execution_id: str) -> dict:
        """GET /workflows/{execution_id}"""

    def get_workflow_results(self, execution_id: str) -> dict:
        """GET /workflows/{execution_id}/results"""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import NetGentServiceClient

netgent = NetGentServiceClient("http://netgent-service:8003")

# List available workflows
workflows = netgent.list_workflows()
print(workflows["workflows"][0]["workflow_id"])

# Execute YouTube workflow
result = netgent.execute_workflow(
    workflow_id="youtube-watch-60s",
    experiment_id="youtube-10mbps-001",
    timeout=120
)
execution_id = result["workflow_execution_id"]

# Check status
status = netgent.get_workflow_status(execution_id)

# Get results when complete
results = netgent.get_workflow_results(execution_id)
print(f"QoE metrics: {results['qoe_metrics']}")
```

---

### StorageServiceClient

**Port**: 8004

```python
class StorageServiceClient(BaseHTTPClient):
    def store_result(self, result: dict) -> dict:
        """POST /results"""

    def get_result(self, result_id: str) -> dict:
        """GET /results/{result_id}"""

    def query_results(self, filters: dict, limit: int = 50,
                     offset: int = 0) -> dict:
        """GET /results?application=...&capacity_min=...&..."""

    def upload_artifact(self, result_id: str, artifact_type: str,
                       file_path: str) -> dict:
        """POST /artifacts (multipart/form-data)"""

    def download_artifact(self, artifact_id: str, save_to: str = None) -> bytes:
        """GET /artifacts/{artifact_id}"""

    def list_artifacts(self, result_id: str) -> dict:
        """GET /results/{result_id}/artifacts"""

    def tag_result(self, result_id: str, tags: list) -> dict:
        """POST /results/{result_id}/tags"""

    def export_csv(self, filters: dict = None) -> bytes:
        """GET /results/export/csv?..."""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import StorageServiceClient

storage = StorageServiceClient("http://storage-service:8004")

# Store experiment result
result_response = storage.store_result({
    "experiment_id": "youtube-10mbps-001",
    "trial_number": 1,
    "status": "success",
    "bottleneck_state": {...},
    "qoe_metrics": {...},
    "contextual_tree": {...}
})
result_id = result_response["result_id"]

# Upload pcap artifact
artifact = storage.upload_artifact(
    result_id=result_id,
    artifact_type="pcap",
    file_path="/tmp/captures/test.pcap"
)

# Query results
results = storage.query_results({
    "application": "youtube",
    "capacity_min": 10,
    "capacity_max": 50
}, limit=100)

# Tag results
storage.tag_result(result_id, ["high-quality", "baseline"])
```

---

## Error Handling

All clients raise descriptive exceptions:

```python
from shared.clients import ClientException, TimeoutException

try:
    result = client.create_experiment({...})
except TimeoutException as e:
    print(f"Request timed out: {e}")
except ClientException as e:
    print(f"Client error: {e}")
```

**Exception Types**:
- `ClientException` — Base exception for all client errors
- `TimeoutException` — Request exceeded timeout
- `ServiceUnavailableException` — Service returned 503 (retried 3 times)
- `ValidationException` — Request validation failed (400)
- `NotFoundExc` — Resource not found (404)

## Testing Clients

```python
# tests/test_clients.py
from unittest.mock import patch, MagicMock
from shared.clients import ExperimentAPIClient

@patch('requests.Session.post')
def test_create_experiment(mock_post):
    mock_post.return_value.json.return_value = {
        "experiment_id": "test-001",
        "status": "pending"
    }

    client = ExperimentAPIClient("http://api:8000")
    result = client.create_experiment({
        "experiment_id": "test-001",
        "capacity_mbps": 10,
        "latency_ms": 50,
        "application": "youtube",
        "duration_seconds": 60
    })

    assert result["experiment_id"] == "test-001"
    mock_post.assert_called_once()
```

## Service Topology

The clients implement the netUnicorn Service-Oriented Architecture (SOA):

```
┌─────────────────────────────────────────────────────────┐
│                    Client Interface                      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│            Experiment API (8000)                        │
│   Orchestration & Intent Plane (Link, Bottleneck)      │
└────┬────────────────────────────────────────────────────┘
     │
     ├──→ CTP Service (8001)      [Representation Plane]
     ├──→ Substrate Worker (8002) [Execution Plane: tc]
     ├──→ NetGent Service (8003)  [Execution Plane: apps]
     └──→ Storage Service (8004)  [Datastore: results]
```

**Data Flow**:
1. User submits Experiment (Intent: capacity, latency, CTP name)
2. Experiment API validates with CTP Service
3. Substrate Worker configures bottleneck via tc
4. NetGent Service executes application workflow
5. All results stored and indexed in Storage Service

## Integration Guidelines

When using clients in a service:

1. **Inject via constructor** — Makes testing easier
   ```python
   class MyService:
       def __init__(self, ctp_client: CTPServiceClient):
           self.ctp = ctp_client
   ```

2. **Use type hints** — Enable IDE autocomplete
   ```python
   from shared.clients import ExperimentAPIClient

   def process(client: ExperimentAPIClient):
       result = client.create_experiment(...)
   ```

3. **Handle exceptions** — All client calls can fail
   ```python
   try:
       result = client.get_experiment(exp_id)
   except ClientException as e:
       logger.error(f"Failed to get experiment: {e}")
       return None
   ```

4. **Log requests** — Clients log automatically, but add context
   ```python
   logger.info(f"Creating experiment: {exp_id}")
   result = client.create_experiment({...})
   logger.info(f"Experiment created: {result['experiment_id']}")
   ```

5. **Follow SOA boundaries** — Use clients to respect service boundaries
   ```python
   # Good: Call through proper service
   ctp_client.validate_ctp(ctp_config)

   # Bad: Direct access to CTP implementation
   from ctp_service.models import CTP
   CTP.validate(ctp_config)  # Breaks SOA
   ```

## Timeout Configuration

Adjust timeouts for specific operations:

```python
# Short timeout for health checks
health_client = ExperimentAPIClient("http://api:8000", timeout=2)

# Long timeout for slow operations
storage_client = StorageServiceClient("http://storage:8004", timeout=30)
```

## Retry Strategy

All clients use exponential backoff with 3 retries:

```
Attempt 1: Immediate
Attempt 2: Wait 1 second
Attempt 3: Wait 2 seconds
Attempt 4: Wait 4 seconds
If all fail: Raise exception
```

Only retries on:
- Connection errors
- 503 Service Unavailable
- 504 Gateway Timeout

Does NOT retry on:
- 400 Bad Request (invalid input)
- 401 Unauthorized
- 404 Not Found

## Architecture and Terminology

**Three-Plane Architecture**:
- **Intent Plane**: User specifies Link() and Bottleneck() intents
- **Representation Plane**: Cross-Traffic Profiles (CTPs) capture temporal demand patterns
- **Execution Plane**: tc (traffic control), tshark (capture), tcpreplay (replay)

**Bottleneck Regime** = Static attributes + Dynamic pressure:
- Static: capacity, base latency, buffering, queue management (AQM)
- Dynamic: CTP temporal structure (extracted, selected, transformed, merged, replayed)

**CTP Operations**:
- `extract()` — Extract CTP from pcap
- `select()` — Select time window or flow subset
- `transform()` — Modify patterns (scale, filter, etc.)
- `merge()` — Combine multiple CTPs
- `replay()` — Replay via tcpreplay

**netUnicorn SOA Components**:
- Client: User interface
- Core/Mediation: Orchestration (Experiment API)
- Deployment: Compiler (CTP Service), Connectivity Manager
- Execution: Processor (Substrate Worker), Gateway (NetGent)
- Datastore: Storage Service

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
**Team**: Prof. Arpit Gupta (PI), Jaber, Eugene, Haarika, Manni, Sylee
**Reference**: OpenClaw (real private SNL-UCSB orchestration framework)
