# CTP Service

**Port**: 8001 · **Plane**: Representation

The CTP (Cross-Traffic Profile) Service turns raw gateway PCAPs into reusable, composable representations of dynamic congestion pressure. A CTP encodes the temporal structure of aggregate demand (intensity, burstiness, heterogeneity, temporal correlation) without binding to the path, applications, or users that produced it. Substrate Worker replays CTPs via `tcpreplay`; CTP Service never touches the kernel.

## Operations

| Operation | Purpose |
|---|---|
| `extract` | Ingest gateway PCAPs and produce a CTP corpus stored in PostgreSQL. |
| `select` | Query the corpus by statistical descriptors (intensity, burstiness, temporal, structure). |
| `transform` | Rescale a CTP to a target capacity via burst trimming (timing preserved). |
| `merge` | Combine `/32` leaf CTPs under a parent subnet across a window range. |
| `replay-data` | Export replay-ready PCAP paths for the Substrate Worker. |

## Extract pipeline

Five steps, all driven by `POST /ctps/extract`:

1. **Split by internal IP** — `app/operations/pcap_split.py`: classifies packets into `users/<ip>/{upload,download}/`.
2. **Split by time window** — `app/operations/window_split.py`: default 30 s windows.
3. **Build timeseries** — `app/operations/extract.py` + `metrics.py`: uses `ip.len` (header, not capture length); default 100 ms bins → 300 bins/window.
4. **Build prefix-hierarchical trees** — `app/trees.py`: leaves are `/32` nodes, parents sum children up to `/16` (`/0`).
5. **Store in PostgreSQL** — `app/database/postgres.py` + `schema.sql`: timeseries as `FLOAT8[]`, descriptors as `JSONB` (GIN indexed).

## Statistical descriptors

`app/operations/metrics.py` computes:

| Category | Fields |
|---|---|
| Intensity | `mean_bps`, `mean_pps`, `peak_bps` |
| Burstiness | `peak_to_mean_ratio` (PMR), `coefficient_of_variation` (CoV), `percentile_95_to_mean`, `on_periods`, `off_periods` |
| Temporal | `lag_1`, `lag_5`, `lag_10`, `lag_60` (Pearson autocorrelation) |
| Structure | `contributor_count`, `upload_download_ratio`, `prefix_diversity` (normalized Shannon entropy of `/24` distribution) |

## API

Interactive docs: `http://localhost:8001/docs`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service + DB connectivity. |
| `GET` | `/ctps` | Paginated corpus listing. |
| `GET` | `/ctps/{ctp_id}` | Full CTP record. |
| `POST` | `/ctps/extract` | Run the full extract pipeline. |
| `POST` | `/ctps/select` | Query by statistical descriptors. |
| `POST` | `/ctps/transform` | Rescale a CTP to a target capacity. |
| `POST` | `/ctps/merge` | Merge leaf CTPs under a parent subnet across a window range. |
| `GET` | `/ctps/{ctp_id}/replay-data` | Resolve/build replay-ready PCAP paths. |

### `GET /ctps`

Query params: `limit` (1–10000, default 50), `offset` (default 0), `order_by` (`intensity` | `burstiness` | `contributor_count` | `window_index`, default `intensity`).

Returns `{total, returned, ctps: [...]}`.

### `POST /ctps/extract`

```json
{
  "pcap_input": "/data/gateway-trace.pcap",
  "output_dir": "/data/ctp-working",
  "dataset_name": "campus-2024-01",
  "window_duration_sec": 30,          // optional
  "burst_interval_ms": 100,           // optional
  "internal_subnets": ["169.231.0.0/16"], // optional
  "workers": 8,                        // optional
  "start_time_epoch": 1700000000       // optional
}
```

Returns `{dataset_name, ctp_count, window_count, user_count, extraction_status, notes}`. `500` on pipeline failure.

### `POST /ctps/select`

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

Returns `{query_matched, results_returned, ctps: [...]}`. All `query` fields are optional.

### `POST /ctps/transform`

```json
{
  "ctp_id": "ctp-campus-169.231.10.1_32-5",
  "output_dir": "/data/output",
  "users_root": "/data/output/users",
  "throughput_threshold_mbps": 10.0
}
```

Caps each interval that exceeds `throughput_threshold_mbps` by randomly dropping packets; preserves burst timing, temporal correlation, and contributor structure. Returns the new CTP id plus output `download_pcap` / `upload_pcap` paths. `404` if `ctp_id` is unknown.

### `POST /ctps/merge`

```json
{
  "dataset_name": "campus-2024-01",
  "subnet": "169.231.0.0/16",
  "start_index": 0,
  "end_index": 29,
  "output_dir": "/data/output",
  "users_root": "/data/output/users"
}
```

Sums leaf timeseries per window and concatenates across windows; merges underlying PCAPs with `joincap`. Returns `{merged_ctp_id, leaf_count, merged_intensity_mbps, download_pcap, upload_pcap, ...}`. `400` if no matching leaves.

### `GET /ctps/{ctp_id}/replay-data`

Query params: `replay_dir` (required), `users_root` (required), `direction` (`download` default, or `upload`).

Returns `{download_pcap, upload_pcap}` paths suitable for Substrate Worker. `404` if the CTP or its leaf PCAPs don't exist.

## CTP object schema

| Field | Type | Notes |
|---|---|---|
| `ctp_id` | string | e.g. `ctp-campus-169.231.10.1/32-5` |
| `dataset_name` | string | Source dataset label |
| `subnet` | string | CIDR (e.g. `169.231.10.1/32`) |
| `window_index` | int | Zero-based window |
| `extracted_from` | string | Source PCAP filename(s) |
| `start_time` | datetime\|null | Wall-clock window start |
| `duration_seconds` | int | Window length |
| `upload_timeseries`, `download_timeseries` | float[] | Per-bin byte counts |
| `intensity` | object | `mean_pps`, `mean_bps`, `mean_mbps`, `peak_pps`, `peak_bps` |
| `burstiness` | object | `peak_to_mean_ratio`, `coefficient_of_variation`, `percentile_95_to_mean`, `on_periods`, `off_periods` |
| `temporal_correlation` | object | `lag_1`, `lag_5`, `lag_10`, `lag_60` |
| `structure` | object | `contributor_count`, `unique_source_ips`, `unique_dest_ips`, `upload_download_ratio`, `prefix_diversity` |
| `is_transformed`, `throughput_threshold_mbps` | bool / float\|null | Set if produced by `/transform` |
| `is_merged`, `merge_start_index`, `merge_end_index` | bool / int\|null | Set if produced by `/merge` |
| `download_pcap`, `upload_pcap` | string\|null | Paths to underlying PCAPs |

## Configuration

All settings come from `CTP_`-prefixed environment variables.

| Variable | Default | Description |
|---|---|---|
| `CTP_DATABASE_URL` | `postgresql://ctp_user:ctp_pass@localhost:5432/ctp_corpus` | PostgreSQL DSN |
| `CTP_HOST` / `CTP_PORT` | `0.0.0.0` / `8001` | Bind |
| `CTP_LOG_LEVEL` | `INFO` | |
| `CTP_WORKERS` | `4` | Parallel worker count |
| `CTP_DB_POOL_MIN` / `CTP_DB_POOL_MAX` | `2` / `10` | Connection pool sizes |
| `CTP_WINDOW_DURATION_SEC` | `30` | Window length |
| `CTP_BURST_INTERVAL_MS` | `100` | Bin width |
| `CTP_START_OFFSET_SEC` | `0` | Leading traffic to discard |
| `CTP_PCAP_BATCH_SIZE` | `30` | Max PCAPs per `joincap` call |
| `CTP_TOP_PREFIX_LEN` | `16` | Shortest prefix in subnet hierarchy |
| `CTP_INTERNAL_SUBNETS` | UCSB defaults | Internal IP prefixes (JSON array) |
| `CTP_GATEWAY_SUBNET` | `169.231.0.0/16` | Top-level gateway subnet |

`docker-compose.yml` also expects:

| Variable | Purpose |
|---|---|
| `CTP_DIR` | Host PCAP input directory (mounted read-only) |
| `CTP_OUTPUT_DIR` | Host output directory (mounted read-write) |

## System dependencies

| Tool | Used for |
|---|---|
| `tshark` | Packet metadata extraction (legacy mode) |
| `joincap` | Merging PCAPs ([releases](https://github.com/assafmo/joincap/releases)) |
| `reordercap` | Reordering packets by timestamp |
| `tcprewrite` | Padding small frames |

Debian/Ubuntu: `apt-get install tshark wireshark-common tcpreplay`.

## Running

```bash
# Local dev
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Via Docker Compose (boots postgres first, then this service)
docker compose up --build ctp-service

# Apply schema manually if needed
psql "$CTP_DATABASE_URL" -f app/database/schema.sql
```

CLI pipeline:

```bash
python -m app.pipeline \
    --mode extract \
    --pcap-input  /data/gateway-trace.pcap \
    --output-dir  /data/ctp-working \
    --dataset-name ucsb-2026-03-04 \
    --database-url "$CTP_DATABASE_URL" \
    --workers 8 --window-duration-sec 30 --burst-interval-ms 100
```

## Tests

```bash
pytest services/ctp-service/tests/ -v
```

## Layout

```
services/ctp-service/
├── app/
│   ├── main.py                      # FastAPI app + lifespan
│   ├── config.py                    # CTP_* settings
│   ├── pipeline.py                  # CLI entry
│   ├── pcap_utils.py                # merge/reorder/pad/trim
│   ├── time_series_modules.py       # PCAP → timeseries
│   ├── tree_node.py / trees.py      # subnet hierarchy
│   ├── api/routes.py                # endpoint handlers
│   ├── database/{postgres.py,schema.sql}
│   ├── models/{ctp.py,descriptors.py}
│   └── operations/{pcap_split,window_split,extract,select,transform,merge,export,metrics}.py
└── tests/
```
