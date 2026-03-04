# HTTP Client Utilities

This directory contains thin HTTP client wrappers for service-to-service communication. All clients inherit from `BaseHTTPClient` for common functionality like retry logic and timeout handling.

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
- 10-second timeout (configurable)
- Request/response logging to stdout
- Proper exception handling and descriptive error messages

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

**Port**: 8001

```python
class CTPServiceClient(BaseHTTPClient):
    def validate_ctp(self, ctp: dict) -> dict:
        """POST /ctps/validate"""

    def compile_ctp(self, ctp: dict, interface: str = "eth0") -> dict:
        """POST /ctps/compile"""

    def get_presets(self) -> dict:
        """GET /ctps/presets"""

    def create_preset(self, preset: dict) -> dict:
        """POST /ctps/presets"""

    def verify_network(self, interface: str, expected_ctp: dict) -> dict:
        """POST /ctps/verify"""

    def health(self) -> dict:
        """GET /health"""
```

**Usage**:
```python
from shared.clients import CTPServiceClient

client = CTPServiceClient("http://ctp-service:8001")
valid, warnings = client.validate_ctp({
    "capacity_mbps": 10,
    "latency_ms": 50,
    "aqm_policy": "fifo"
})
if valid:
    commands = client.compile_ctp({...}, interface="eth0")
```

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

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
