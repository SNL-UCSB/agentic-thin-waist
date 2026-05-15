# Experiment API

**Port**: 8000 · **Plane**: Intent

The Experiment API is the controller surface for the Intent plane. It accepts an experiment specification, coordinates downstream services (CTP, Substrate Worker, NetGent, Telemetry), and exposes the experiment's status and aggregated results. In the current codebase it is a thin Flask stub that persists experiment specs in-memory; most of the orchestration logic lives in the Orchestration Service (:8005), which drives Substrate Worker (:8002) and Telemetry (:8004) directly.

## Current endpoints

Implemented in `app/main.py`. The store is in-memory — restarting the service drops all experiments.

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/health` | Returns `{"status":"healthy"}`. |
| `GET` | `/status` | Returns configured downstream URLs and `experiments_total`. |
| `GET` | `/experiments` | Lists all in-memory experiment records. |
| `POST` | `/experiments` | Persists an experiment spec. Requires `experiment_id`; returns `409` if it already exists. |
| `GET` | `/experiments/<experiment_id>` | Returns the stored record, or `404`. |

### Example

```bash
# Create an experiment
curl -X POST http://localhost:8000/experiments \
  -H 'Content-Type: application/json' \
  -d '{
    "experiment_id": "iperf_40_100_cubic_001",
    "capacity_mbps": 40,
    "latency_ms": 100,
    "aqm_policy": "fq_codel",
    "applications": [{"application":"iperf","workflow_spec":"iperf-60s"}],
    "duration_seconds": 60,
    "num_trials": 1
  }'

# Read it back
curl http://localhost:8000/experiments/iperf_40_100_cubic_001
```

## Intended specification (not yet enforced)

The fields the controller will eventually validate and act on:

```python
@dataclass
class BottleneckStatic:
    capacity_mbps: float
    latency_ms: float
    buffer_size: int
    aqm_policy: str  # "fifo", "codel", "pie", "fq_codel", "cake"

@dataclass
class BottleneckDynamic:
    ctp_name: str
    ctp_operations: list[str]  # extract, select, transform, merge

@dataclass
class Experiment:
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    buffer_size: int
    aqm_policy: str
    ctp_name: str
    ctp_operations: list[str]
    applications: list[dict]    # [{application, workflow_spec}, …]
    duration_seconds: int
    num_trials: int = 1
    capture_pcap: bool = True
    metadata: dict = field(default_factory=dict)
    status: str = "pending"
```

An **experiment** can contain multiple **iterations**. Each iteration pairs one network configuration with one or more concurrent applications. Multiple applications in a single iteration share the same bottleneck, which captures interference effects (e.g., YouTube and Zoom competing on a 10 Mbps link).

## Controller pattern

The Experiment API is a *smart controller* in front of *dumb services*. Each downstream service (CTP, Substrate Worker, NetGent, Telemetry) accepts one configuration at a time and returns a result; it does not track iteration counts or sequencing. The controller owns:

- pre-flight checks (CTP replay-ready, NetGent workflow generated, Substrate Worker reachable),
- per-iteration dispatch and state-machine transitions,
- result aggregation into a final `ExperimentResult` written to Telemetry.

Planned state machine: `pending → provisioning → replay_warmup → executing → collecting → complete` (or `failed`).

## Downstream integration points

| Service | Endpoints used | Purpose |
|---|---|---|
| CTP Service (:8001) | `POST /ctps/select`, `POST /ctps/transform`, … | Validate/transform the requested CTP, produce replay-ready PCAP. |
| Substrate Worker (:8002) | `POST /shape`, `POST /capture/start`, `POST /replay`, `POST /capture/stop` | Apply tc/netem, run tcpreplay, capture traffic. |
| NetGent Service (:8003) | `POST /workflows/generate`, `POST /workflows/execute`, `GET /workflows/result/{job_id}` | Generate/execute browser or shell workflow. |
| Telemetry Service (:8004) | `POST /results`, `POST /artifacts` | Persist result rows and artifacts. |

Each service's own README documents its full HTTP surface.

## Environment

| Variable | Purpose |
|---|---|
| `CTP_SERVICE_URL` | e.g. `http://ctp-service:8001` |
| `SUBSTRATE_WORKER_URL` | e.g. `http://substrate-worker:8002` |
| `NETGENT_SERVICE_URL` | e.g. `http://netgent-service:8003` |
| `TELEMETRY_SERVICE_URL` | e.g. `http://telemetry-service:8004` |

## Run locally

```bash
# Within the docker-compose stack
docker compose up -d experiment-api
curl http://localhost:8000/health

# Standalone (Python)
pip install -r requirements.txt
FLASK_APP=app.main:app flask run --port 8000
```

## Tests

```bash
pytest services/experiment-api/tests/ -v
```
