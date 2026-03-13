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
    └── test_placeholder.py
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

- Primary key: `(dataset_name, subnet, window_index)`
- Timeseries stored as `FLOAT8[]` native arrays
- Statistical descriptors stored as `JSONB`
- B-tree indexes on `mean_mbps`, `pmr`, `cov`, `lag_1`, `contributor_count`

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

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ctps/extract` | POST | Run full extract pipeline |
| `/ctps/select` | POST | Query corpus by statistical descriptors |
| `/ctps/transform` | POST | Rescale CTP to target capacity |
| `/ctps/merge` | POST | Compose CTPs by window concat or weighted sum |
| `/ctps/{id}/replay-data` | GET | Export replay-ready PCAP for Substrate Worker |
| `/ctps/{id}` | GET | Full CTP details |
| `/ctps` | GET | Paginated corpus listing |
| `/health` | GET | Service health + PostgreSQL connectivity |

Interactive API docs: `http://localhost:8001/docs`

---

## Configuration

All settings are controlled by environment variables prefixed `CTP_`.

| Variable | Default | Description |
|----------|---------|-------------|
| `CTP_DATABASE_URL` | `postgresql://ctp_user:ctp_pass@localhost:5432/ctp_corpus` | PostgreSQL connection URL |
| `CTP_PORT` | `8001` | TCP port |
| `CTP_LOG_LEVEL` | `INFO` | Logging level |
| `CTP_WORKERS` | `4` | Parallel worker count |
| `CTP_WINDOW_DURATION_SEC` | `30` | Time-window length |
| `CTP_BURST_INTERVAL_MS` | `100` | Timeseries bin width (ms) |
| `CTP_INTERNAL_SUBNETS` | UCSB defaults | Internal IP prefix list (JSON array) |
| `CTP_GATEWAY_SUBNET` | `169.231.0.0/16` | Top-level gateway subnet |

---

## Running

### Start the service

```bash
# Development
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Production
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

**Last Updated**: 2026-03-13
**Status**: Active Development
**Team Lead**: Jaber
**PI**: Prof. Arpit Gupta
**Repository**: agentic-thin-waist/services/ctp-service
