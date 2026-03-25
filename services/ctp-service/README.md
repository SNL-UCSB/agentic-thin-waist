# CTP Service

**Port**: 8001
**Deliverable**: D1 (Network Virtualization Substrate - Representation Plane)
**Lead**: Jaber | **Supporting**: Satyam, Snithik
**PI**: Prof. Arpit Gupta
**Priority**: CRITICAL
**Status**: Active Development

---

## Purpose

The CTP (Cross-Traffic Profile) Service is the **Representation Plane** of the bottleneck in the Agentic Thin Waist architecture. It transforms passive packet traces from production networks into reusable, composable representations of dynamic congestion pressure—enabling systematic experimentation with realistic traffic conditions without binding to specific paths, applications, or users.

A CTP is a reusable representation of dynamic congestion pressure applied at a bottleneck, encoding temporal structure of aggregate demand (intensity, burstiness, heterogeneity, temporal correlations) without binding to particular paths, applications, or users that produced it.

---

## Architecture

```
┌────────────────────────────────────┐
│   Experiment Controller (Port 8000) │
│   or External Research Client       │
└────────────┬────────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│   CTP SERVICE (Port 8001)           │
│  ┌──────────────────────────────┐  │
│  │ CTP Operations Engine        │  │
│  │ • extract() — traces → CTPs  │  │
│  │ • select() — query by attrs  │  │
│  │ • transform() — adapt CTP    │  │
│  │ • merge() — compose CTPs     │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ CTP Index & Storage          │  │
│  │ PostgreSQL — ctp_nodes table │  │
│  └──────────────────────────────┘  │
└────────────┬────────────────────────┘
             │ Replay-ready PCAP
             ▼
        ┌────────────────────┐
        │ Substrate Worker   │
        │ :8002 (tcpreplay)  │
        └────────────────────┘
```

---

## Directory Structure

```
services/ctp-service/
├── Dockerfile
├── requirements.txt
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app + lifespan
│   ├── config.py                   # Pydantic-settings configuration
│   ├── pipeline.py                 # CLI entry point (extract + legacy modes)
│   ├── pcap_utils.py               # PCAP merge/reorder/pad/trim utilities
│   ├── time_series_modules.py      # PCAP → TimeSeries conversion
│   ├── tree_node.py                # TreeNode data structure + metrics
│   ├── trees.py                    # Subnet tree construction + serialisation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── ctp.py                  # CTP dataclasses
│   │   └── descriptors.py          # Pydantic request/response models
│   ├── database/
│   │   ├── __init__.py
│   │   ├── postgres.py             # PostgreSQL connection pool + data access
│   │   └── schema.sql              # CREATE TABLE + indexes DDL
│   ├── operations/
│   │   ├── __init__.py
│   │   ├── pcap_split.py           # Step 1: split by internal IP
│   │   ├── window_split.py         # Step 2: split by time windows
│   │   ├── metrics.py              # Statistical descriptor computation
│   │   ├── extract.py              # Steps 1–5 orchestrator
│   │   ├── select.py               # Select operation
│   │   ├── transform.py            # Transform operation
│   │   ├── merge.py                # Merge operation
│   │   └── export.py               # Export replay-ready PCAPs
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # FastAPI endpoint handlers
│   └── utils/
│       ├── __init__.py
│       └── logging.py              # Structured logging setup
└── tests/
    ├── __init__.py
    ├── conftest.py                 # pytest fixtures; stubs heavy deps (numpy, scapy, psycopg2)
    ├── test_placeholder.py         # Placeholder test
    └── test_routes.py              # Unit tests for all API endpoints (mocked DB + operations)
```

---

## Extract Pipeline (Steps 1–5)

The **Extract** operation converts raw gateway PCAP files into the CTP corpus stored in PostgreSQL.

### Step 1 — Split PCAPs by Internal IP

`app/operations/pcap_split.py`

- Input: gateway PCAP file(s) or directory
- Streams packets; classifies by source/destination IP against `internal_subnets`
- **Upload** = internal source IP → `users/<ip>/upload/<stem>.pcap`
- **Download** = internal destination IP → `users/<ip>/download/<stem>.pcap`
- Parallel processing across multiple input PCAPs

### Step 2 — Split by Time Windows

`app/operations/window_split.py`

- Input: per-user upload/download PCAPs
- Default window: 30 seconds (configurable)
- Output: `window_0001.pcap`, `window_0002.pcap`, … under `windows/` subdirectory
- Boundary determined by first-packet timestamp

### Step 3 — Build Timeseries

`app/operations/extract.py` + `app/operations/metrics.py`

- Input: per-window PCAPs
- **Uses `ip.len` from IP header** (not captured payload length)
- Default bin width: 100 ms → 300 bins per 30-second window
- Output: `numpy.ndarray` of byte counts per bin

### Step 4 — Build Prefix-Hierarchical Trees

`app/trees.py` + `app/tree_node.py`

- Leaf nodes: /32 per-user nodes
- Hierarchy: /32 → /31 → /30 → … → /16 → /0
- Parent timeseries = element-wise sum of children
- Metrics computed at every node: burstiness, throughput, asymmetry, median

### Step 5 — Store in PostgreSQL

`app/database/postgres.py` + `app/database/schema.sql`

- Primary key: `ctp_id`
- Timeseries stored as `FLOAT8[]` native arrays
- Statistical descriptors stored as `JSONB`
- B-tree indexes on `mean_mbps`, `pmr`, `cov`, `lag_1`, `contributor_count`, `(dataset_name, window_index)`
- GIN indexes on `intensity` and `structure` JSONB columns for arbitrary queries
- `datasets` table stores capture-level metadata (window duration, bin width, gateway subnet, totals)

---

## Statistical Descriptors

`app/operations/metrics.py`

| Category | Metric | Description |
|----------|--------|-------------|
| Intensity | `mean_bps` | Mean bit rate (bits/s) |
| Intensity | `mean_pps` | Estimated mean packet rate |
| Intensity | `peak_bps` | Peak bit rate |
| Burstiness | `peak_to_mean_ratio` (PMR) | max / mean |
| Burstiness | `coefficient_of_variation` (CoV) | std / mean |
| Burstiness | `percentile_95_to_mean` | P95 / mean |
| Burstiness | `on_periods` / `off_periods` | Contiguous active/idle runs |
| Temporal | `lag_1`, `lag_5`, `lag_10`, `lag_60` | Pearson autocorrelation |
| Structure | `contributor_count` | Number of /32 leaf users |
| Structure | `upload_download_ratio` | Upload bytes / download bytes |
| Structure | `prefix_diversity` | Normalised Shannon entropy of /24 distribution |

---

## API Endpoints

Interactive API docs: `http://localhost:8001/docs`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service health + PostgreSQL connectivity |
| `/ctps` | GET | Paginated corpus listing |
| `/ctps/{id}` | GET | Full CTP details |
| `/ctps/extract` | POST | Run full extract pipeline |
| `/ctps/select` | POST | Query corpus by statistical descriptors |
| `/ctps/transform` | POST | Rescale CTP to target capacity |
| `/ctps/merge` | POST | Compose CTPs by window concat + weighted sum |
| `/ctps/{id}/replay-data` | GET | Export replay-ready PCAP for Substrate Worker |

---

### `GET /health`

Returns service health and PostgreSQL connectivity.

**Returns**
```json
{
  "status": "healthy",
  "postgresql_connected": true,
  "service_version": "1.0.0",
  "python_version": "...",
  "platform": "..."
}
```
`status` is `"degraded"` if the database is unreachable.

---

### `GET /ctps`

Paginated listing of all CTPs in the corpus.

**Query parameters**

| Parameter | Default | Description |
|---|---|---|
| `limit` | `50` | Max results (1–10 000) |
| `offset` | `0` | Pagination offset |
| `order_by` | `intensity` | Sort field: `intensity` \| `burstiness` \| `contributor_count` \| `window_index` |

**Returns**
```json
{
  "total": 1200,
  "returned": 50,
  "ctps": [ { "ctp_id": "...", "subnet": "...", ... } ]
}
```

---

### `GET /ctps/{ctp_id}`

Full details and all statistical descriptors for a single CTP.

**Path parameter**: `ctp_id` — unique identifier assigned during extraction.

**Returns** a single CTP object (see [CTP Object Schema](#ctp-object-schema)).

**Errors**: `404` if not found.

---

### `POST /ctps/extract`

Ingests raw PCAP traces and runs the full five-step extraction pipeline to produce CTPs stored in PostgreSQL.

**Steps**: split by IP → split by time window → build timeseries → build prefix tree → store in DB.

**Request body**

| Field | Required | Description |
|---|---|---|
| `pcap_input` | yes | Absolute path to a PCAP file or directory of PCAPs |
| `output_dir` | yes | Root directory for intermediate per-user PCAP files |
| `dataset_name` | yes | Human-readable label for this dataset |
| `window_duration_sec` | no | Override default window size (seconds) |
| `burst_interval_ms` | no | Override default bin width (ms) |
| `internal_subnets` | no | Override default internal IP prefixes |
| `workers` | no | Override default parallel worker count |
| `start_time_epoch` | no | Unix timestamp of the first packet |

**Returns**
```json
{
  "dataset_name": "campus-2024-01",
  "ctp_count": 840,
  "window_count": 30,
  "user_count": 28,
  "extraction_status": "success",
  "notes": null
}
```

**Errors**: `500` on pipeline failure with a detail message.

---

### `POST /ctps/select`

Queries the corpus using multi-dimensional statistical filter criteria. All filter fields are optional.

**Request body**
```json
{
  "query": {
    "dataset_name": "campus-2024-01",
    "subnet_prefix_len": 32,
    "intensity_range_mbps": [1.0, 50.0],
    "burstiness_pmr_range": [1.0, 10.0],
    "burstiness_cov_range": [0.0, 2.0],
    "temporal_correlation_min": 0.5,
    "contributor_count_min": 1,
    "contributor_count_max": 100,
    "upload_download_ratio_max": 2.0,
    "window_index_range": [0, 29]
  },
  "limit": 50,
  "offset": 0,
  "order_by": "intensity"
}
```

**Returns**
```json
{
  "query_matched": 143,
  "results_returned": 50,
  "ctps": [ { "ctp_id": "...", ... } ]
}
```

---

### `POST /ctps/transform`

Rescales a CTP to a target bottleneck capacity by applying a hard throughput threshold (burst trimming). Burst timing, temporal correlation, and contributor structure are preserved. The resulting CTP is saved to the corpus.

**Request body**

| Field | Required | Description |
|---|---|---|
| `ctp_id` | yes | ID of the CTP to transform |
| `output_dir` | yes | Root directory for output PCAP files (`<output_dir>/<dataset>_transformed/`) |
| `users_root` | yes | Root of the per-user PCAP directory from extraction |
| `throughput_threshold_mbps` | yes | Hard cap in Mbps; packets in intervals exceeding this rate are randomly dropped |
| `preserve_structure` | no | Always `true`; structure is never modified |

**Returns**
```json
{
  "original_ctp_id": "ctp-campus-169.231.10.1_32-5",
  "transformed_ctp_id": "ctp-transform-ctp-campus-169.231.10.1_32-5-10mbps",
  "throughput_threshold_mbps": 10.0,
  "download_pcap": "/data/output/campus_transformed/downlink/ctp-campus-169.231.10.1_32-5_10mbps_download.pcap",
  "upload_pcap": "/data/output/campus_transformed/uplink/ctp-campus-169.231.10.1_32-5_10mbps_upload.pcap",
  "notes": "Trimming Done; temporal structure and asymmetry preserved."
}
```

**Errors**: `404` if `ctp_id` not found; `500` on processing failure.

---

### `POST /ctps/merge`

Merges all `/32` leaf CTPs under a parent subnet across a range of window indices. Timeseries are summed per window and concatenated across windows; underlying PCAPs are merged with `joincap`. The resulting CTP is stored in the corpus.

Output PCAPs are written to:
```
<output_dir>/<dataset_name>_merged/downlink/<ctp_id>_download.pcap
<output_dir>/<dataset_name>_merged/uplink/<ctp_id>_upload.pcap
```

**Request body**

| Field | Required | Description |
|---|---|---|
| `dataset_name` | yes | Dataset label |
| `subnet` | yes | Parent CIDR subnet whose `/32` leaf nodes will be merged |
| `start_index` | yes | First window index (inclusive, ≥ 0) |
| `end_index` | yes | Last window index (inclusive, must be ≥ `start_index`) |
| `output_dir` | yes | Root directory for merged PCAP output |
| `users_root` | yes | Root of the per-user PCAP directory tree from extraction |

**Returns**
```json
{
  "merged_ctp_id": "ctp-merged-campus-2024-01-169-231-0-0_16-0-29",
  "dataset_name": "campus-2024-01",
  "subnet": "169.231.0.0/16",
  "start_index": 0,
  "end_index": 29,
  "leaf_count": 28,
  "merged_intensity_mbps": 312.4,
  "merged_contributor_count": 28,
  "download_pcap": "/data/output/campus-2024-01_merged/downlink/ctp-merged-campus-2024-01-..._download.pcap",
  "upload_pcap": "/data/output/campus-2024-01_merged/uplink/ctp-merged-campus-2024-01-..._upload.pcap",
  "notes": "Merged 28 leaf IP(s) across windows 0–29."
}
```

**Errors**: `400` if no matching leaf CTPs are found; `500` on processing failure.

---

### `GET /ctps/{ctp_id}/replay-data`

Exports a CTP as a replay-ready PCAP file for the Substrate Worker. Locates or generates the merged PCAP and returns it as a binary file download.

**Path parameter**: `ctp_id` — CTP identifier.

**Query parameters**

| Parameter | Required | Description |
|---|---|---|
| `replay_dir` | yes | Root directory for replay PCAP output |
| `users_root` | yes | Root of the per-user PCAP directory from extraction |
| `direction` | no | `download` (default) or `upload` |

**Returns**
```json
{
  "download_pcap": "/data/replay/<dataset>_replay/downlink/<ctp_id>_download.pcap",
  "upload_pcap": "/data/replay/<dataset>_replay/uplink/<ctp_id>_upload.pcap"
}
```

**Errors**: `404` if the CTP does not exist or no leaf PCAPs are found.

---

## CTP Object Schema

Every CTP object returned by the API contains:

| Field | Type | Description |
|---|---|---|
| `ctp_id` | string | Unique identifier (e.g. `ctp-campus-169.231.10.1/32-5`) |
| `dataset_name` | string | Source dataset label |
| `subnet` | string | CIDR subnet (e.g. `169.231.10.1/32`) |
| `window_index` | int | Zero-based time-window index |
| `extracted_from` | string | Source PCAP filename(s) |
| `start_time` | datetime \| null | Wall-clock window start |
| `duration_seconds` | int | Window length in seconds |
| `upload_timeseries` | float[] | Per-bin byte counts for outbound traffic |
| `download_timeseries` | float[] | Per-bin byte counts for inbound traffic |
| `intensity` | object | `mean_pps`, `mean_bps`, `mean_mbps`, `peak_pps`, `peak_bps` |
| `burstiness` | object | `peak_to_mean_ratio`, `coefficient_of_variation`, `percentile_95_to_mean`, `on_periods`, `off_periods` |
| `temporal_correlation` | object | Autocorrelation at `lag_1`, `lag_5`, `lag_10`, `lag_60` |
| `structure` | object | `contributor_count`, `unique_source_ips`, `unique_dest_ips`, `upload_download_ratio`, `prefix_diversity` |
| `is_transformed` | bool | `true` if produced by `/ctps/transform` |
| `throughput_threshold_mbps` | float \| null | Threshold used during transform |
| `is_merged` | bool | `true` if produced by `/ctps/merge` |
| `merge_start_index` | int \| null | First window index in merge range |
| `merge_end_index` | int \| null | Last window index in merge range |
| `download_pcap` | string \| null | Path to download PCAP |
| `upload_pcap` | string \| null | Path to upload PCAP |

---

## Configuration

All settings are controlled by environment variables prefixed `CTP_`.

| Variable | Default | Description |
|----------|---------|-------------|
| `CTP_DATABASE_URL` | `postgresql://ctp_user:ctp_pass@localhost:5432/ctp_corpus` | PostgreSQL connection URL |
| `CTP_HOST` | `0.0.0.0` | Bind address |
| `CTP_PORT` | `8001` | TCP port |
| `CTP_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`) |
| `CTP_WORKERS` | `4` | Parallel worker count |
| `CTP_DB_POOL_MIN` | `2` | Minimum DB connections in pool |
| `CTP_DB_POOL_MAX` | `10` | Maximum DB connections in pool |
| `CTP_WINDOW_DURATION_SEC` | `30` | Time-window length (seconds) |
| `CTP_BURST_INTERVAL_MS` | `100` | Timeseries bin width (ms) |
| `CTP_START_OFFSET_SEC` | `0` | Leading traffic to discard at capture start (seconds) |
| `CTP_PCAP_BATCH_SIZE` | `30` | Max PCAPs joined per `joincap` call |
| `CTP_TOP_PREFIX_LEN` | `16` | Shortest prefix length in the subnet hierarchy (`/16` = gateway) |
| `CTP_INTERNAL_SUBNETS` | UCSB defaults | Internal IP prefix list (JSON array) |
| `CTP_GATEWAY_SUBNET` | `169.231.0.0/16` | Top-level gateway subnet |

---

## Running

### Start the service

```bash
# Development
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Production (via Docker — uses gunicorn + UvicornWorker)
docker-compose up postgres ctp-service
```

### Run the CLI pipeline (Extract)

```bash
# Full extract: gateway PCAP → PostgreSQL
python -m app.pipeline \
    --mode extract \
    --pcap-input /data/gateway-trace.pcap \
    --output-dir /data/ctp-working \
    --dataset-name ucsb-2026-03-04 \
    --database-url postgresql://user:pass@localhost:5432/ctp_corpus \
    --workers 8 \
    --window-duration-sec 30 \
    --burst-interval-ms 100

# Legacy mode: pre-split user PCAPs → JSON trees
python -m app.pipeline \
    --mode legacy \
    --pcap-dir /data/pcaps \
    --ts-dir /data/timeseries \
    --tree-dir /data/trees \
    --mask 169.231 \
    --time-limit 15
```

### Apply the database schema

```bash
psql $CTP_DATABASE_URL -f app/database/schema.sql
```

### Select CTPs

```bash
curl -X POST http://localhost:8001/ctps/select \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "intensity_range_mbps": [100, 3000],
      "burstiness_pmr_range": [2.0, 5.0],
      "temporal_correlation_min": 0.3,
      "contributor_count_min": 10
    },
    "limit": 20,
    "order_by": "intensity"
  }'
```

### Extract CTPs from a PCAP

```bash
curl -X POST http://localhost:8001/ctps/extract \
  -H "Content-Type: application/json" \
  -d '{
    "pcap_input": "/home/netreplica/config/ctp/out_70_profile8.pcap",
    "output_dir": "/home/netreplica/output_test",
    "dataset_name": "test_dataset"
  }'
```

### Transform a CTP

```bash
curl -X POST http://localhost:8001/ctps/transform \
  -H "Content-Type: application/json" \
  -d '{
    "ctp_id": "ctp-test_dataset-169.231.162.180_30-w0001",
    "throughput_threshold_mbps": 4,
    "output_dir": "/home/netreplica/output_test",
    "users_root": "/home/netreplica/output_test/users"
  }'
```

### Merge CTPs across a window range

```bash
curl -X POST http://localhost:8001/ctps/merge \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_name": "test_dataset",
    "subnet": "169.231.180.0/30",
    "start_index": 1,
    "end_index": 2,
    "output_dir": "/home/netreplica/output_test",
    "users_root": "/home/netreplica/output_test/users"
  }'
```

### Export replay-ready PCAP paths

```bash
curl -X GET \
  "http://localhost:8001/ctps/ctp-test_dataset-169.231.162.176_28-w0001/replay-data?replay_dir=/home/netreplica/output_test&users_root=/home/netreplica/output_test/users&direction=download"
```

---

## System Dependencies

| Tool | Purpose |
|------|---------|
| `tshark` | Packet metadata extraction (legacy mode) |
| `joincap` | PCAP merging |
| `reordercap` | Packet reordering |
| `tcprewrite` | Packet padding |

Install on Debian/Ubuntu:
```bash
apt-get install tshark wireshark-common tcpreplay
# joincap: see https://github.com/assafmo/joincap/releases
```

---

## Testing

```bash
pytest services/ctp-service/tests/ -v
```

---

---

## Docker Setup and Usage

### Step 1 — Build the Image

Run from the repo root:

```bash
cd agentic-thin-waist/
sudo docker build -t ctp-service -f services/ctp-service/Dockerfile .
```

### Step 2 — Start Infrastructure

#### 2a. Create a shared Docker network

```bash
sudo docker network create ctp-net
```

#### 2b. Start PostgreSQL

```bash
sudo docker run -d \
  --name ctp-postgres \
  --network ctp-net \
  -e POSTGRES_USER=ctp_user \
  -e POSTGRES_PASSWORD=ctp_pass \
  -e POSTGRES_DB=ctp_corpus \
  -v pgdata:/var/lib/postgresql/data \
  postgres:15
```

#### 2c. Apply the database schema

```bash
sudo docker exec -i ctp-postgres psql \
  -U ctp_user -d ctp_corpus \
  < services/ctp-service/app/database/schema.sql
```

### Step 3 — Configure Environment

Create `services/ctp-service/.env`:

```ini
CTP_DATABASE_URL=postgresql://ctp_user:ctp_pass@ctp-postgres:5432/ctp_corpus
CTP_PORT=8001
CTP_LOG_LEVEL=INFO
CTP_WORKERS=4
CTP_WINDOW_DURATION_SEC=30
CTP_BURST_INTERVAL_MS=100
CTP_GATEWAY_SUBNET=169.231.0.0/16
```

### Step 4 — Start the CTP Service

Replace the two `-v` mount paths with your actual input and output directories.

```bash
sudo docker run \
  --name ctp-service \
  --network ctp-net \
  -p 8001:8001 \
  --env-file services/ctp-service/.env \
  --cap-add=NET_ADMIN \
  -v /path/to/pcap/input:/path/to/pcap/input:ro \
  -v /path/to/output/dir:/path/to/output/dir \
  ctp-service
```

### Step 5 — API Usage Examples

#### Health check

```bash
curl http://localhost:8001/health
```

#### List all CTPs

```bash
curl http://localhost:8001/ctps
```

#### Extract

```bash
curl -X POST http://localhost:8001/ctps/extract \
  -H "Content-Type: application/json" \
  -d '{
    "pcap_input": "/path/to/pcap/input/your-trace.pcap",
    "output_dir": "/path/to/output/dir",
    "dataset_name": "your-dataset-name"
  }'
```

#### Select

```bash
curl -X POST http://localhost:8001/ctps/select \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "dataset_name": "your-dataset-name",
      "intensity_range_mbps": [3.5, 4.5]
    },
    "limit": 20,
    "order_by": "contributor_count"
  }'
```

#### Transform

```bash
curl -X POST http://localhost:8001/ctps/transform \
  -H "Content-Type: application/json" \
  -d '{
    "ctp_id": "ctp-your-dataset-name-169.231.162.180_30-w0001",
    "throughput_threshold_mbps": 1,
    "output_dir": "/path/to/output/dir",
    "users_root": "/path/to/output/dir/users"
  }'
```

#### Merge

```bash
curl -X POST http://localhost:8001/ctps/merge \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_name": "your-dataset-name",
    "subnet": "169.231.162.180/30",
    "start_index": 1,
    "end_index": 2,
    "output_dir": "/path/to/output/dir",
    "users_root": "/path/to/output/dir/users"
  }'
```

#### Replay Data

```bash
curl -X GET \
  "http://localhost:8001/ctps/ctp-your-dataset-name-169.231.162.180_30-w0001/replay-data?replay_dir=/path/to/output/dir&users_root=/path/to/output/dir/users&direction=download"
```

---

**Last Updated**: 2026-03-25
**Status**: Active Development
**Team Lead**: Jaber
**PI**: Prof. Arpit Gupta
**Repository**: agentic-thin-waist/services/ctp-service
