# Testing Guide

This directory contains unit, integration, and end-to-end tests for the Agentic Thin Waist project.

## Test Structure

```
tests/
├── README.md                        # This file
├── __init__.py
├── conftest.py                      # pytest fixtures and config
│
├── unit/                            # Unit tests (fast, isolated)
│   ├── test_experiment_api.py
│   ├── test_ctp_service.py
│   ├── test_substrate_worker.py
│   ├── test_netgent_service.py
│   ├── test_storage_service.py
│   ├── test_orchestration.py
│   └── test_shared_models.py
│
├── integration/                     # Integration tests (medium, require services)
│   ├── test_experiment_lifecycle.py      # Full workflow
│   ├── test_bottleneck_verification.py   # D1 core tests
│   ├── test_workflow_execution.py        # D2 tests
│   ├── test_result_storage.py            # D3 tests
│   └── test_orchestration_end_to_end.py  # D5 tests
│
└── fixtures/                        # Test data
    ├── sample_experiments.json
    ├── sample_results.json
    └── sample_workflows.json
```

## Running Tests

### All Tests
```bash
# From project root
make test

# Or directly with pytest
pytest tests/ -v
```

### Unit Tests Only (Fast)
```bash
pytest tests/unit/ -v
```

### Integration Tests (Slower, requires services)
```bash
# Start services first
make up

# Then run tests
pytest tests/integration/ -v
```

### Specific Test File
```bash
pytest tests/unit/test_experiment_api.py -v
```

### Specific Test Function
```bash
pytest tests/unit/test_experiment_api.py::test_create_experiment -v
```

### With Coverage Report
```bash
pytest tests/ --cov=app --cov-report=html
# Open htmlcov/index.html
```

## Test Categories

### Unit Tests (Fast, Isolated)

Test individual functions and classes without external dependencies.

**Characteristics**:
- No network calls
- No database access
- Mock all external dependencies
- Run in < 1 second each
- Should pass offline

**Example**:
```python
# tests/unit/test_ctp_service.py
import pytest
from app.engine.validator import CTPValidator

def test_validate_ctp_valid():
    validator = CTPValidator()
    valid, warnings = validator.validate_ctp(
        capacity_mbps=10,
        latency_ms=50,
        loss_rate=0
    )
    assert valid == True
    assert len(warnings) == 0

def test_validate_ctp_invalid_capacity():
    validator = CTPValidator()
    valid, warnings = validator.validate_ctp(
        capacity_mbps=-1,
        latency_ms=50,
        loss_rate=0
    )
    assert valid == False
    assert "capacity" in str(warnings).lower()
```

### Integration Tests (Medium Speed)

Test interaction between services. Requires services to be running.

**Characteristics**:
- Call real HTTP endpoints
- Use test database or in-memory storage
- Test workflows across multiple services
- Run in < 10 seconds each
- Require `make up` first

**Example**:
```python
# tests/integration/test_experiment_lifecycle.py
import pytest
import requests
from shared.models import Experiment

@pytest.fixture
def api_client():
    return requests.Session()

def test_full_experiment_lifecycle(api_client):
    # 1. Create experiment
    exp = {
        "experiment_id": "test-001",
        "capacity_mbps": 10,
        "latency_ms": 50,
        "application": "youtube",
        "duration_seconds": 30
    }
    response = api_client.post(
        "http://localhost:8000/experiments",
        json=exp
    )
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "pending"

    # 2. Execute experiment
    response = api_client.post(
        f"http://localhost:8000/experiments/{exp['experiment_id']}/execute"
    )
    assert response.status_code == 202

    # 3. Poll until complete
    import time
    for _ in range(60):  # 60 second timeout
        response = api_client.get(
            f"http://localhost:8000/experiments/{exp['experiment_id']}"
        )
        status = response.json()["status"]
        if status == "complete":
            break
        time.sleep(1)

    # 4. Verify results
    response = api_client.get(
        f"http://localhost:8000/experiments/{exp['experiment_id']}/results"
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results["results"]) > 0
```

## Fixtures

### conftest.py

Shared fixtures for all tests:

```python
# tests/conftest.py
import pytest
from app.main import create_app

@pytest.fixture
def client():
    """Flask test client."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_experiment():
    """Sample experiment for testing."""
    return {
        "experiment_id": "test-exp-001",
        "capacity_mbps": 10,
        "latency_ms": 50,
        "application": "youtube",
        "duration_seconds": 30
    }

@pytest.fixture
def sample_result():
    """Sample experiment result."""
    return {
        "experiment_id": "test-exp-001",
        "trial_number": 1,
        "status": "success",
        "bottleneck_state": {
            "configured_capacity": 10.0,
            "configured_latency": 50,
            "measured_throughput": 9.8,
            "measured_rtt": 52,
            "verification_passed": True
        },
        "qoe_metrics": {
            "video_startup_time_ms": 2500,
            "mean_bitrate_mbps": 8.5
        },
        "contextual_tree": {...}
    }
```

## Test Data

### fixtures/sample_experiments.json

Pre-defined test experiments:

```json
[
  {
    "experiment_id": "youtube-10mbps-001",
    "capacity_mbps": 10,
    "latency_ms": 50,
    "application": "youtube",
    "duration_seconds": 30
  },
  {
    "experiment_id": "zoom-25mbps-001",
    "capacity_mbps": 25,
    "latency_ms": 30,
    "application": "zoom",
    "duration_seconds": 300
  }
]
```

Load in tests:
```python
import json

with open('tests/fixtures/sample_experiments.json') as f:
    experiments = json.load(f)
```

## Coverage Goals

| Component | Unit | Integration | Coverage |
|-----------|------|-------------|----------|
| Experiment API | 15 tests | 5 tests | 85% |
| CTP Service | 20 tests | 3 tests | 90% |
| Substrate Worker | 10 tests | 2 tests | 80% |
| NetGent Service | 8 tests | 3 tests | 75% |
| Storage Service | 15 tests | 4 tests | 85% |
| Orchestration | 12 tests | 2 tests | 70% |
| **Total** | **80 tests** | **19 tests** | **80%** |

## Running CI Locally

Simulate GitHub Actions locally:

```bash
# Install tox
pip install tox

# Run full CI suite
tox

# Run specific environment
tox -e py310
tox -e lint
tox -e type-check
```

### Tox Environments

```ini
[tox]
envlist = py310, lint, type-check, cov

[testenv]
deps = pytest, pytest-cov, requests
commands = pytest tests/ --cov=app

[testenv:lint]
commands = flake8 app/ services/

[testenv:type-check]
commands = mypy app/ services/

[testenv:cov]
commands = pytest tests/ --cov=app --cov-report=html
```

## Debugging Tests

### Run with Logging
```bash
pytest tests/ -v -s --log-cli-level=DEBUG
```

### Drop into Debugger
```python
def test_something():
    import pdb; pdb.set_trace()  # Execution pauses here
    result = function_under_test()
```

### Use pytest-watch for TDD
```bash
# Auto-run tests on file changes
pip install pytest-watch
ptw tests/
```

## Mocking External Services

```python
from unittest.mock import patch, MagicMock

def test_with_mocked_service():
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = {"status": "ok"}

        # Code that calls requests.post
        result = some_function_that_calls_api()

        # Assert mock was called correctly
        mock_post.assert_called_once_with(...)
        assert result["status"] == "ok"
```

## Load Testing

For performance testing:

```bash
# Install locust
pip install locust

# Run load test
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

**locustfile.py**:
```python
from locust import HttpUser, task

class APIUser(HttpUser):
    @task
    def create_experiment(self):
        self.client.post(
            "/experiments",
            json={"experiment_id": "test", ...}
        )
```

## CI/CD Integration

Tests run automatically on:
- Push to any branch
- Pull requests
- Scheduled nightly (full suite)

See `.github/workflows/tests.yml` for configuration.

## Writing New Tests

1. **Name clearly**: `test_<function>_<scenario>`
   ```python
   def test_create_experiment_with_valid_parameters():
   def test_create_experiment_with_invalid_capacity():
   ```

2. **Use fixtures**: Reuse common setup
   ```python
   def test_something(client, sample_experiment):
       # client and sample_experiment are provided
   ```

3. **Assert specifically**: Use descriptive assertions
   ```python
   assert response.status_code == 201, f"Expected 201, got {response.status_code}"
   assert "error" not in response.json()
   ```

4. **Group related tests**: Use test classes
   ```python
   class TestExperimentCreation:
       def test_valid_parameters(self):
           ...
       def test_invalid_parameters(self):
           ...
   ```

5. **Clean up after yourself**: Use fixtures or teardown
   ```python
   @pytest.fixture
   def temp_file(tmp_path):
       f = tmp_path / "test.txt"
       yield f
       # Cleanup happens automatically
   ```

---

**Last Updated**: 2026-03-04
**Status**: Testing framework ready
**Next Milestone**: Complete unit tests for D1 services (Week 1-2)
