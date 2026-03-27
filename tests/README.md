# Testing Guide: Agentic Thin Waist

This guide covers the testing pyramid, per-service strategies, and how to validate the four core requirements: controllability, composability, fidelity, and replicability.

**Lead**: Sylee (Architecture Review, CI/CD, Testing Infrastructure)

---

## Testing Pyramid

The testing pyramid defines the breadth and depth of testing at each level:

```
         ┌─────────────────────┐
         │   End-to-End Tests  │  (Few, slow, full workflows)
         ├─────────────────────┤
         │ Service Integration │  (Medium, slower, cross-service)
         ├─────────────────────┤
         │    Unit Tests       │  (Many, fast, single function)
         ├─────────────────────┤
         │ Schema Validation   │  (Many, very fast, dataclass checks)
         └─────────────────────┘
```

### Level 1: Schema Validation (Fastest)

Validate dataclass contracts before any code execution:
- Confirm `Experiment`, `BottleneckState`, `ExperimentResult` schemas
- Check type correctness and required fields
- Verify range constraints (e.g., capacity_mbps > 0)
- Test dataclass serialization/deserialization

**When to use**: Every PR that touches `shared/models/`

### Level 2: Unit Tests (Fast, Isolated)

Test individual functions and classes without external dependencies:
- No network calls, no database access
- Mock all external dependencies
- Run in <1 second each
- Should pass offline

**When to use**: All service code, utility functions, validators

### Level 3: Service Integration (Medium Speed)

Test interaction between services. Requires services running via Docker Compose:
- Call real HTTP endpoints
- Use test database or in-memory storage
- Test workflows across multiple services
- Run in <10 seconds each

**When to use**: Cross-service workflows, full experiment lifecycle

### Level 4: End-to-End (Slowest)

Full workflow testing in realistic conditions:
- Complete experiment from Intent → Representation → Execution
- Include browser automation (D2), storage (D3), orchestration (D5)
- Measure closed-loop fidelity
- Validate replicability across runs

**When to use**: Pre-release validation, critical user paths

---

## Test Structure

> **Unit tests live inside each service's own `tests/` folder.** The top-level `tests/` directory is reserved for cross-service integration tests, end-to-end tests, and shared fixtures.

### Per-Service Unit Tests

```
services/
├── experiment-api/tests/               # D1: Experiment API unit tests
├── ctp-service/tests/                  # D1: CTP Service unit tests
├── substrate-worker/tests/             # D1: Substrate Worker unit tests
├── netgent-service/tests/              # D2: NetGent Service unit tests
├── telemetry-service/tests/            # D3: Telemetry Service unit tests
└── orchestration/tests/                # D5: Orchestration Service unit tests

shared/tests/                           # Shared models and clients unit tests
```

Each service's `tests/` directory contains:
- `__init__.py` — Package marker
- `conftest.py` — Service-specific fixtures (to be created)
- `test_*.py` — Unit test modules (to be created)

### Cross-Service Tests (this directory)

```
tests/
├── README.md                           # This file
├── __init__.py
├── conftest.py                         # (To be created) Global pytest fixtures
│
├── integration/                        # Level 3: Service integration
│   ├── test_netgent_telemetry_integration.py # D2↔D3 workflow artifact/result handoff
│   └── test_orchestration_integration.py     # D5 orchestration against downstream services
│
├── e2e/                                # Level 4: End-to-end tests
│   ├── test_full_experiment.py         # Complete workflow Intent→Execution
│   ├── test_browser_scenario.py        # Browser automation scenarios
│   └── test_fidelity_validation.py     # Closed-loop realism checks
│
└── fixtures/                           # Test data and utilities
    ├── conftest_shared.py              # Shared fixtures
    ├── sample_experiments.json         # Test experiment specs
    ├── sample_results.json             # Test results
    ├── sample_workflows.json           # Test NFA workflows
    └── bottleneck_scenarios.json       # Common bottleneck regimes
```

---

## Running Tests

### Quick Start

```bash
# Run all tests (unit + integration + e2e)
make test

# Or with pytest directly
pytest tests/ services/*/tests/ shared/tests/ -v
```

### By Level

```bash
# Unit tests only (fast) — from each service's tests/ folder
pytest services/*/tests/ shared/tests/ -v

# Integration tests only (medium speed, requires Docker Compose)
pytest tests/integration/ -v

# All tests including E2E (full validation)
pytest services/*/tests/ shared/tests/ tests/ -v
```

### By Service (D1, D2, D3, D5)

```bash
# D1 Foundation unit tests
pytest services/experiment-api/tests/ services/ctp-service/tests/ services/substrate-worker/tests/ -v

# D2 Application unit tests
pytest services/netgent-service/tests/ -v

# D3 Data Layer unit tests
pytest services/telemetry-service/tests/ -v

# D5 Intelligence unit tests
pytest services/orchestration/tests/ -v

# Shared library unit tests
pytest shared/tests/ -v
```

### With Coverage

```bash
# Generate coverage report
pytest services/*/tests/ shared/tests/ tests/ --cov=app --cov=shared --cov-report=html
open htmlcov/index.html

# Coverage by service
pytest services/experiment-api/tests/ --cov=services.experiment_api.app --cov-report=term-missing
```

### Integration Tests (Requires Docker Compose)

```bash
# Start services
make up

# Run integration tests
pytest tests/integration/ -v

# Clean up
make down
```

### E2E Tests

```bash
# Start full stack
make up

# Run E2E tests
pytest tests/e2e/ -v

# Full validation run
pytest tests/ -v
```

---

## Testing the Four Requirements

Every service must satisfy controllability, composability, fidelity, and replicability. Here's how to test each.

### Requirement 1: Controllability

**Definition**: Monotonic attribute changes produce predictable, proportional behavior.

**Testing strategy**: Vary static bottleneck attributes (capacity, latency, loss) individually and verify QoE metrics respond monotonically.

```python
# tests/unit/d1/test_d1_four_requirements.py

def test_controllability_capacity():
    """Increasing capacity should monotonically improve throughput."""
    capacities = [5, 10, 20, 50]
    throughputs = []

    for cap in capacities:
        result = ctp_service.simulate(
            capacity_mbps=cap,
            latency_ms=50,
            loss_rate=0,
            duration_s=10
        )
        throughputs.append(result.measured_throughput)

    # Verify monotonic increase
    assert all(throughputs[i] <= throughputs[i+1]
               for i in range(len(throughputs)-1))

def test_controllability_latency():
    """Increasing latency should monotonically worsen QoE."""
    latencies = [10, 25, 50, 100]
    qoe_scores = []

    for lat in latencies:
        result = substrate_worker.execute(
            bottleneck_regime=BottleneckState(
                capacity_mbps=10,
                latency_ms=lat,
                loss_rate=0
            ),
            duration_s=10
        )
        qoe_scores.append(result.qoe_metric)

    # Verify monotonic decrease in QoE
    assert all(qoe_scores[i] >= qoe_scores[i+1]
               for i in range(len(qoe_scores)-1))
```

### Requirement 2: Composability

**Definition**: Static and dynamic attributes compose correctly and predictably.

**Testing strategy**: Verify that combining static (capacity, latency) with dynamic (congestion pressure) produces expected aggregate behavior.

```python
# tests/integration/test_four_requirements.py

def test_composability_static_and_dynamic():
    """Static + dynamic attributes should compose predictably."""

    # Test Case 1: Static capacity + no congestion
    static_only = ctp_service.compose(
        static_attrs=BottleneckState(
            capacity_mbps=10,
            latency_ms=50,
            loss_rate=0
        ),
        dynamic_attrs=DynamicCongestion(pressure=0)
    )

    # Test Case 2: Same static + light congestion
    with_congestion = ctp_service.compose(
        static_attrs=BottleneckState(
            capacity_mbps=10,
            latency_ms=50,
            loss_rate=0
        ),
        dynamic_attrs=DynamicCongestion(pressure=0.3)
    )

    # Composability: congestion should degrade throughput monotonically
    assert with_congestion.effective_capacity < static_only.effective_capacity

    # Composability: composition should be predictable (loss/latency unchanged)
    assert with_congestion.latency_ms == static_only.latency_ms
    assert with_congestion.loss_rate == static_only.loss_rate

def test_composability_order_independence():
    """Composition order should not affect result."""

    result_a = ctp_service.compose(
        static=BottleneckState(capacity_mbps=10, latency_ms=50, loss_rate=0),
        dynamic=DynamicCongestion(pressure=0.5)
    )

    result_b = ctp_service.compose(
        dynamic=DynamicCongestion(pressure=0.5),
        static=BottleneckState(capacity_mbps=10, latency_ms=50, loss_rate=0)
    )

    assert result_a.effective_capacity == result_b.effective_capacity
```

### Requirement 3: Fidelity

**Definition**: Closed-loop realism is preserved throughout execution.

**Testing strategy**: Run experiments with known outcomes and verify the system behaves like real networks.

```python
# tests/integration/test_bottleneck_verification.py

def test_fidelity_youtube_streaming():
    """YouTube streaming on 10Mbps/50ms should match real-world behavior."""

    result = experiment_api.run(
        experiment=Experiment(
            experiment_id="fidelity-yt-001",
            ctp=BottleneckState(
                capacity_mbps=10,
                latency_ms=50,
                loss_rate=0.005
            ),
            application="youtube",
            duration_s=60
        )
    )

    # Real YouTube on 10Mbps/50ms typically:
    # - Startup time: 2-4 seconds
    # - Mean bitrate: 6-8 Mbps (adaptive)
    # - Rebuffering: none or minimal
    assert result.qoe.video_startup_time_ms < 4000
    assert 6 <= result.qoe.mean_bitrate_mbps <= 8
    assert result.qoe.rebuffer_count <= 1

def test_fidelity_zoom_conferencing():
    """Zoom on 2.5Mbps/25ms should preserve closed-loop video quality."""

    result = experiment_api.run(
        experiment=Experiment(
            experiment_id="fidelity-zoom-001",
            ctp=BottleneckState(
                capacity_mbps=2.5,
                latency_ms=25,
                loss_rate=0.01
            ),
            application="zoom",
            duration_s=300
        )
    )

    # Zoom on 2.5Mbps should maintain video but may show quality drops
    assert result.qoe.video_available_percent > 90
    assert result.qoe.latency_perception == "acceptable"
```

### Requirement 4: Replicability

**Definition**: Same specification produces comparable results across runs.

**Testing strategy**: Run the same experiment multiple times and verify variance is within acceptable bounds.

```python
# tests/integration/test_four_requirements.py

def test_replicability_same_spec():
    """Same experiment spec should produce comparable results."""

    spec = Experiment(
        experiment_id="replicate-test",
        ctp=BottleneckState(
            capacity_mbps=10,
            latency_ms=50,
            loss_rate=0
        ),
        application="youtube",
        duration_s=30
    )

    # Run 5 times
    results = []
    for i in range(5):
        result = experiment_api.run(
            Experiment(
                experiment_id=f"replicate-test-{i}",
                **spec.dict()
            )
        )
        results.append(result.qoe.mean_bitrate_mbps)

    # Compute coefficient of variation
    mean = sum(results) / len(results)
    variance = sum((x - mean) ** 2 for x in results) / len(results)
    std_dev = variance ** 0.5
    cv = std_dev / mean

    # CV should be < 5% for replicability
    assert cv < 0.05, f"Coefficient of variation {cv} exceeds 5% threshold"

def test_replicability_across_substrates():
    """Same spec on different substrates should produce comparable results."""

    spec = Experiment(
        ctp=BottleneckState(
            capacity_mbps=10,
            latency_ms=50,
            loss_rate=0
        ),
        application="youtube",
        duration_s=30
    )

    # Run on different substrate implementations
    result_linux = substrate_worker_linux.execute(spec)
    result_macos = substrate_worker_macos.execute(spec)
    result_windows = substrate_worker_windows.execute(spec)

    results = [
        result_linux.qoe.mean_bitrate_mbps,
        result_macos.qoe.mean_bitrate_mbps,
        result_windows.qoe.mean_bitrate_mbps
    ]

    # All results within 10% of each other
    max_result = max(results)
    min_result = min(results)
    assert (max_result - min_result) / min_result < 0.10
```

---

## Per-Service Testing Guide

### D1: Foundation (Network Virtualization) — Jaber, Satyam, Snithik

**Core tests**:
```bash
pytest services/experiment-api/tests/ services/ctp-service/tests/ services/substrate-worker/tests/ -v
```

**What to test**:
1. Experiment API: CRUD operations, lifecycle state machine
2. CTP Service: Bottleneck regime validation, monotonicity
3. Substrate Worker: Execution fidelity, attribute composition
4. All four requirements: controllability, composability, fidelity, replicability

**Key scenarios**:
- Create experiment with valid/invalid CTP
- Verify bottleneck state attributes compose correctly
- Run same experiment twice and verify replicability (CV < 5%)

### D2: Application Layer — Eugene + Jaber

**Core tests**:
```bash
pytest services/netgent-service/tests/ -v
```

**What to test**:
1. NetGent Service: Browser automation commands
2. NFA Workflow: Navigation and action sequences
3. Cross-service handoff to Telemetry Service

**Key scenarios**:
- Execute NFA workflow and verify artifacts/results can be handed to Telemetry
- Verify actions complete within expected time
- Capture and verify QoE metrics (startup time, bitrate, rebuffering)

### D3: Data Layer — Manni

**Core tests**:
```bash
pytest services/telemetry-service/tests/ -v
```

**What to test**:
1. Telemetry Service: CRUD for results, artifacts
2. Query API: Filter, sort, aggregate results
3. Schema validation: ExperimentResult and ContextualTreeNode

**Key scenarios**:
- Store result with metadata and contextual tree
- Query results by experiment_id, ctp, application
- Verify result retrieval and serialization

### D5: Intelligence — Haarika

**Core tests**:
```bash
pytest services/orchestration/tests/ -v
```

**What to test**:
1. Orchestration Service: Claude + downstream service coordination
2. Intent → experiment translation
3. Experiment orchestration based on intent

**Key scenarios**:
- Translate research intent to experiment spec
- Dispatch and monitor downstream experiment execution
- Aggregate results across downstream services

---

## Shared Fixtures and Setup

### conftest.py

```python
import pytest
from app.main import create_app
from shared.models import Experiment, BottleneckState

@pytest.fixture
def client():
    """Flask/FastAPI test client."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_ctp():
    """Standard CTP for testing."""
    return BottleneckState(
        capacity_mbps=10,
        latency_ms=50,
        loss_rate=0.005
    )

@pytest.fixture
def sample_experiment(sample_ctp):
    """Standard experiment for testing."""
    return Experiment(
        experiment_id="test-exp-001",
        ctp=sample_ctp,
        application="youtube",
        duration_s=30
    )

@pytest.fixture
def docker_services():
    """Fixture for integration tests with Docker Compose."""
    # Start services via docker-compose
    yield
    # Teardown
```

---

## Coverage Goals

| Component | Unit | Integration | E2E | Target |
|-----------|------|-------------|-----|--------|
| Experiment API (D1) | 15 | 5 | 2 | 90% |
| CTP Service (D1) | 25 | 5 | 2 | 95% |
| Substrate Worker (D1) | 15 | 3 | 1 | 85% |
| NetGent Service (D2) | 12 | 4 | 2 | 80% |
| Telemetry Service (D3) | 18 | 4 | 1 | 85% |
| Orchestration (D5) | 14 | 3 | 2 | 75% |
| Shared Models | 10 | 2 | 0 | 95% |
| **Total** | **109** | **26** | **10** | **85%** |

---

## CI/CD Integration

### GitHub Actions

Tests run automatically on:
- Push to any branch
- Pull requests (blocking)
- Scheduled nightly (full suite including E2E)

**Workflow levels**:
- PR: Schema + Unit + Integration (fast, 5 min timeout)
- Main: Schema + Unit + Integration + E2E (comprehensive, 30 min timeout)
- Nightly: Full suite with coverage report

See `.github/workflows/tests.yml` for configuration.

### Local Simulation

```bash
# Install tox
pip install tox

# Run full CI suite
tox

# Run specific environment
tox -e py310-unit
tox -e py310-integration
tox -e lint
tox -e type-check
```

---

## Best Practices

1. **Name clearly**: `test_<component>_<scenario>_<expected_outcome>`
   ```python
   def test_ctp_controllability_capacity_increases_throughput():
   def test_composability_static_and_dynamic_compose_predictably():
   ```

2. **Use fixtures**: Reuse common setup across tests
   ```python
   def test_something(client, sample_ctp, sample_experiment):
       # Fixtures are automatically provided
   ```

3. **Test the four requirements**: Every service should validate controllability, composability, fidelity, replicability

4. **Mock external services**: Isolate unit tests from network/database
   ```python
   from unittest.mock import patch

   @patch('requests.post')
   def test_with_mock(mock_post):
       mock_post.return_value.json.return_value = {"status": "ok"}
   ```

5. **Assert with context**: Provide meaningful error messages
   ```python
   assert cv < 0.05, f"CV {cv:.3f} exceeds 5% threshold for replicability"
   ```

6. **Clean up**: Use fixtures for resource management
   ```python
   @pytest.fixture
   def temp_file(tmp_path):
       f = tmp_path / "test.json"
       yield f
       # Automatic cleanup
   ```

---

## Debugging Tests

```bash
# Run with verbose output and logging
pytest tests/ -v -s --log-cli-level=DEBUG

# Drop into debugger on failure
pytest tests/ --pdb

# Run specific test with timing
pytest tests/unit/d1/test_ctp_service.py::test_controllability_capacity -v --durations=0

# Generate profile
pytest tests/ --profile

# Use pytest-watch for TDD
pip install pytest-watch
ptw tests/ -- -v
```

---

**Lead**: Sylee (Architecture Review, CI/CD, Testing Infrastructure)
**D1 Team**: Jaber, Satyam, Snithik
**Last Updated**: 2026-03-04
**Status**: Testing pyramid framework established
**Next Milestone**: Complete unit tests for D1 services (Week 1-2), 80% coverage by Week 3
