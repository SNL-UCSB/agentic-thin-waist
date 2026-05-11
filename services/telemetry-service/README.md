# Telemetry Service

**Port**: 8004 · **Plane**: Representation (data layer)

Centralized persistence and query layer for experiment results, artifacts, and orchestration records. Every result is tagged with a four-layer **contextual tree** so callers can filter by static network config, dynamic measured state, application, and transport details. Backed by SQLAlchemy + PostgreSQL (production) or SQLite (dev). Artifacts are stored in S3/MinIO.

## Contextual tree

Every `Result` row carries a `contextual_tree` JSONB blob with four layers:

| Layer | Holds | Examples |
|---|---|---|
| `c_static` | Configured bottleneck attributes | `capacity_mbps`, `latency_ms`, `buffer_size`, `aqm_policy` |
| `c_dyn` | Measured runtime state | `ctp_cluster_id`, `measured_throughput`, `measured_rtt` |
| `c_app` | Application context | `application`, `workflow_spec` |
| `c_trans` | Transport details | `protocol`, `congestion_control` |

`c_app.application` is also extracted into the top-level `application` column for fast filtering.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service liveness. |
| `POST` | `/results` | Store an experiment result. |
| `GET` | `/results` | Filtered query. |
| `GET` | `/results/{result_id}` | Single result. |
| `POST` | `/results/{result_id}/tags` | Append tags (deduplicated). |
| `GET` | `/results/{result_id}/artifacts` | List artifacts attached to a result. |
| `GET` | `/results/export/csv` | CSV export (≤10 000 rows). |
| `POST` | `/artifacts` | Upload an artifact (multipart). |
| `GET` | `/artifacts/{artifact_id}` | Stream/download an artifact. |
| `PUT` | `/orchestrations/{orch_id}` | Upsert an orchestration record. |
| `GET` | `/orchestrations/{orch_id}` | Read an orchestration record. |
| `DELETE` | `/orchestrations/{orch_id}` | Remove an orchestration record. |

### `POST /results`

```json
{
  "experiment_id": "iperf_40_100_cubic_001",
  "trial_number": 1,
  "status": "success",
  "bottleneck_state": {
    "configured_capacity": 40.0,
    "configured_latency": 100,
    "measured_throughput": 39.6,
    "measured_rtt": 101
  },
  "pcap_path": "s3://artifacts/.../trial-1.pcap",
  "qoe_metrics":  { "video_startup_time_ms": 2500, "mean_bitrate_mbps": 8.5, ... },
  "transport_state": { "throughput_mbps": 39.6, "rtt_ms": 101, "packet_loss": 0.001 },
  "contextual_tree": {
    "c_static": { "capacity_mbps": 40, "latency_ms": 100, "aqm_policy": "fq_codel" },
    "c_dyn":    { "measured_throughput": 39.6, "measured_rtt": 101 },
    "c_app":    { "application": "iperf", "workflow_spec": "iperf-60s" },
    "c_trans":  { "protocol": "tcp", "congestion_control": "cubic" }
  }
}
```

Required: `experiment_id`, `status`. Other fields are optional but recommended. Response (201) includes the assigned `result_id` (UUID).

### `GET /results`

| Param | Purpose |
|---|---|
| `experiment_id` | Exact match. |
| `application` | Matches `c_app.application` (cached column). |
| `capacity_min`, `capacity_max` | Range on `configured_capacity`. |
| `latency_min`, `latency_max` | Range on `configured_latency`. |
| `congestion_control` | Matches `c_trans.congestion_control` (JSONB). |
| `created_after`, `created_before` | ISO 8601 timestamps. |
| `tags` | Comma-separated, requires all to be present. |
| `limit` | Default 50, max 500. |
| `offset` | Default 0. |
| `sort_by` | Result column (default `created_at`). |
| `sort_order` | `asc` | `desc` (default). |

Returns `{results, total, limit, offset, returned}`.

> **Heads-up**: this endpoint does **not** currently filter by `orchestration_id`. If you need per-orchestration results, query orchestration:8005 first to collect the experiment IDs, then call `GET /results?experiment_id=…` for each.

### `POST /artifacts`

`multipart/form-data` with `result_id`, `artifact_type` (default `log`), and `file`. The blob is uploaded to S3/MinIO under `artifacts/{result_id}/{artifact_id}/{filename}`. Returns the artifact metadata row.

### Orchestration records

```bash
# Upsert
curl -X PUT http://localhost:8004/orchestrations/orch-abc12345 \
  -H 'Content-Type: application/json' \
  -d '{"status":"complete", "intent":"...", "results":[...]}'

# Fetch
curl http://localhost:8004/orchestrations/orch-abc12345

# Delete
curl -X DELETE http://localhost:8004/orchestrations/orch-abc12345
```

The orchestration service uses these to persist its run records.

### `GET /results/export/csv`

Accepts the same filters as `/results`. Columns:

```
result_id, experiment_id, trial_number, application, status, created_at,
configured_capacity, configured_latency, measured_throughput, measured_rtt,
video_startup_time_ms, mean_bitrate_mbps, bitrate_changes,
rebuffer_events, rebuffer_duration_ms,
congestion_control, protocol,
pcap_path, tags
```

Refuses with `400` if the filtered set exceeds 10 000 rows.

## Schema

```sql
CREATE TABLE results (
    result_id           VARCHAR(64) PRIMARY KEY,
    experiment_id       VARCHAR(64) NOT NULL,
    trial_number        INT,
    application         VARCHAR(32),
    status              VARCHAR(32),
    configured_capacity FLOAT,
    configured_latency  FLOAT,
    measured_throughput FLOAT,
    measured_rtt        FLOAT,
    qoe_metrics         JSONB,
    transport_state     JSONB,
    contextual_tree     JSONB,
    pcap_path           VARCHAR(512),
    tags                TEXT[],
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_exp_app_date ON results (experiment_id, application, created_at);

CREATE TABLE artifacts (
    artifact_id   VARCHAR(64) PRIMARY KEY,
    result_id     VARCHAR(64) REFERENCES results(result_id),
    artifact_type VARCHAR(32),
    filename      VARCHAR(256),
    size_bytes    BIGINT,
    storage_path  VARCHAR(512),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orchestrations (
    orchestration_id VARCHAR(64) PRIMARY KEY,
    status           VARCHAR(32),
    payload          JSONB,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Dependencies

- **PostgreSQL** (production) / SQLite (dev) — relational store + JSONB filtering.
- **S3 / MinIO** — artifact blob storage. The `minio-init` sidecar in `docker-compose.yml` creates the required bucket on startup.

## Configuration

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL DSN parts. |
| `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Artifact storage. |
| `S3_CONNECTION_RETRIES`, `S3_CONNECTION_TIMEOUT_SECONDS` | Retry/back-off. |

## Run locally

```bash
docker compose up -d telemetry-service
curl http://localhost:8004/health
```

## Tests

```bash
pytest services/telemetry-service/tests/ -v
```

## Source layout

```
services/telemetry-service/
└── app/telemetry/
    ├── app.py        # Flask factory
    ├── db.py         # SQLAlchemy session
    ├── models.py     # Result, Artifact, Orchestration
    ├── routes.py     # All HTTP routes
    ├── s3.py         # S3/MinIO helpers
    └── commands.py   # CLI helpers
```
